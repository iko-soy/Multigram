#!/usr/bin/env python3
"""Report a "Sync with Forkgram" run on the GitHub issue labelled forkgram-sync.

Runs in the report job of .github/workflows/sync-forkgram.yml, after the sync, compile and
promote jobs. It reads their results and the sync outputs from the environment and:

  - conflict, compile failure, promote failure, a sync error, or a multigram-next changed by
    hand that the sync would have replaced: opens an issue, or comments on the open one, with
    what happened and the local commands to fix it (the same event is reported once, however
    often the schedule runs);
  - multigram still behind with no new release: opens an issue only if none is open;
  - promoted, or multigram in step with Forkgram: closes the open issue with a note (naming
    any MultiGram commits the new multigram leaves out).

Environment: SYNC_RESULT, COMPILE_RESULT, PROMOTE_RESULT (job results); SYNC_* (the sync
job's outputs, e.g. SYNC_STATUS, SYNC_FORKGRAM_VERSION); PROMOTE_TAG; RUN_URL; GH_TOKEN
and GH_REPO for the gh CLI. REPORT_GH names another gh binary (the self-test uses a fake).
Standard library only.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile

LABEL = 'forkgram-sync'
GH = os.environ.get('REPORT_GH', 'gh')
SHA = re.compile(r'^[0-9a-f]{40}$')
VERSION = re.compile(r'^[0-9A-Za-z][0-9A-Za-z._+-]{0,39}$')


def env(name):
    return os.environ.get(name, '').strip()


def sha(name):
    value = env(name)
    return value if SHA.match(value) else ''


def short(value):
    return value[:10] if value else '?'


def version():
    value = env('SYNC_FORKGRAM_VERSION')
    return value if VERSION.match(value) else 'unknown'


def block(text):
    """Untrusted text (commit subjects, file names, errors) as a Markdown code block."""
    text = text.replace('`', "'").strip() or '(none)'
    return '```text\n' + text + '\n```'


def gh(*args):
    run = subprocess.run([GH, *args], capture_output=True, text=True)
    if run.returncode != 0:
        sys.stderr.write(run.stderr)
        raise SystemExit(f'gh {args[0]} {args[1] if len(args) > 1 else ""} failed')
    return run.stdout


def gh_body(*args, body):
    with tempfile.NamedTemporaryFile('w', suffix='.md', delete=False) as f:
        f.write(body)
        path = f.name
    try:
        return gh(*args, '--body-file', path)
    finally:
        os.unlink(path)


def open_issues():
    issues = json.loads(gh('issue', 'list', '--label', LABEL, '--state', 'open',
                           '--json', 'number,title', '--limit', '20') or '[]')
    return sorted(i['number'] for i in issues)


def open_issue():
    numbers = open_issues()
    return numbers[0] if numbers else None


def already_reported(number, key):
    data = json.loads(gh('issue', 'view', str(number), '--json', 'body,comments'))
    texts = [data.get('body') or ''] + [c.get('body') or '' for c in data.get('comments', [])]
    return any(key in t for t in texts)


def marker(key):
    return f'<!-- forkgram-sync-key: {key} -->'


def title():
    return f'Forkgram sync needs a hand (Forkgram {version()})'


def run_line():
    url = env('RUN_URL')
    return f'Run: {url}' if url.startswith('https://') else ''


def use_next_step():
    return ('Then open **Actions > Sync with Forkgram > Run workflow**, tick **use_next** and run '
            'it. It compiles `multigram-next` and, if that passes, moves `multigram` to it (the '
            'old tip is kept as the tag `multigram-before-<version>`) and closes this issue.')


def body_conflict():
    snap, prev = sha('SYNC_SNAPSHOT') or '<new snapshot>', sha('SYNC_PREVIOUS_SNAPSHOT') or '<old snapshot>'
    commit = sha('SYNC_CONFLICT_COMMIT')
    return f"""**Forkgram {version()}** is out and is now on `forkgram` (snapshot `{short(snap)}`), but the MultiGram stack does not apply to it. `multigram` is unchanged.

MultiGram commit `{short(commit)}` ({env('SYNC_CONFLICT_POSITION') or '?'}) stops the rebase:
{block(env('SYNC_CONFLICT_SUBJECT'))}
Files:
{block(env('SYNC_CONFLICT_DETAILS') or env('SYNC_CONFLICT_FILES'))}
{run_line()}

### Fix it locally

```sh
git fetch origin
git switch -C multigram-next origin/multigram
git config rerere.enabled true     # reuses your fixes if you redo this rebase in this clone
git rebase --onto {snap} {prev}
# fix the files git names, then:
git add <files>
git rebase --continue              # repeat until the rebase is done
git push --force origin multigram-next
```

To leave a MultiGram commit out instead (Forkgram now does the same thing, say), run `git rebase --skip` at that commit.

{use_next_step()}
"""


def body_compile():
    snap, cand = sha('SYNC_SNAPSHOT') or '<snapshot>', sha('SYNC_CANDIDATE')
    return f"""The MultiGram stack applied cleanly to **Forkgram {version()}**, but the compile check failed. `multigram` is unchanged; the candidate is on `multigram-next` (`{short(cand)}`).

{run_line()}

If the log shows a runner or network hiccup, use **Re-run failed jobs** on the run page. Otherwise:

### Fix it locally

```sh
git fetch origin
git switch -C multigram-next origin/multigram-next
# fix the build, then fold the fix into the MultiGram commit it belongs to:
git commit -a --fixup=<that commit>
GIT_SEQUENCE_EDITOR=: git rebase -i --autosquash {snap}
git push --force origin multigram-next
```

{use_next_step()}
"""


def body_promote():
    cand = sha('SYNC_CANDIDATE')
    return f"""The candidate for **Forkgram {version()}** compiled, but moving `multigram` to it failed, usually because someone pushed to `multigram` or `multigram-next` while the sync ran. `multigram` is unchanged; the candidate is still on `multigram-next` (`{short(cand)}`).

{run_line()}

Check that `multigram-next` holds everything `multigram` has now (rebase any new commits onto it and push it), then run **Actions > Sync with Forkgram** with **use_next**.
"""


def body_error():
    return f"""The sync stopped with an error. Nothing was pushed after the error; `multigram` is unchanged.

{block(env('SYNC_ERROR') or env('SYNC_MESSAGE') or 'The sync job failed before it could say why; see the run log.')}
{run_line()}

Fix the cause (the message says what it is), then run **Actions > Sync with Forkgram** again.
"""


def body_next_edited():
    nxt, tip, fc = sha('SYNC_EXISTING_NEXT'), sha('SYNC_FORKGRAM_TIP'), sha('SYNC_FORKGRAM_COMMIT')
    if tip and tip != fc:
        what = f"Forkgram's `dev` has moved on (`{short(tip)}`), but the sync did not take it"
    else:
        what = 'The sync was asked to rebuild `multigram-next` (force), but did not'
    return f"""{what}: `multigram-next` (`{short(nxt)}`) has commits the sync did not make, most likely a fix by hand, and the sync never replaces those. Nothing was pushed; `forkgram` and `multigram` are unchanged.

{run_line()}

- If `multigram-next` is ready, run **Actions > Sync with Forkgram > Run workflow** with **use_next**: it compiles `multigram-next` and, if that passes, moves `multigram` to it. The next scheduled sync then takes the new Forkgram commit.
- If you do not need it any more, delete it (`git push origin --delete multigram-next`); the next sync rebuilds it from `multigram`.
"""


def body_behind():
    return f"""`forkgram` has **Forkgram {version()}** (snapshot `{short(sha('SYNC_SNAPSHOT'))}`), but `multigram` is still based on the older snapshot `{short(sha('SYNC_MULTIGRAM_BASE'))}`: an earlier sync could not move it and no issue is open about it.

{run_line()}

Run **Actions > Sync with Forkgram** with **force** to try again; if the stack still does not apply, this issue gets the details and the commands to fix it.
"""


def report(key, body):
    number = open_issue()
    text = marker(key) + '\n' + body
    if number is None:
        gh('label', 'create', LABEL, '--color', 'D93F0B', '--force',
           '--description', 'The automatic sync with Forkgram needs a hand')
        print(gh_body('issue', 'create', '--title', title(), '--label', LABEL, body=text).strip())
        return
    if key and already_reported(number, marker(key)):
        print(f'issue #{number} already reports this; nothing to add')
        return
    gh('issue', 'edit', str(number), '--title', title())
    gh_body('issue', 'comment', str(number), body=text)
    print(f'commented on issue #{number}')


def close(note):
    for number in open_issues():
        gh('issue', 'close', str(number), '--reason', 'completed', '--comment', note)
        print(f'closed issue #{number}')


def main():
    results = [env('SYNC_RESULT'), env('COMPILE_RESULT'), env('PROMOTE_RESULT')]
    status = env('SYNC_STATUS')
    print(f'sync={results[0]} compile={results[1]} promote={results[2]} status={status or "-"}')
    if 'cancelled' in results:
        print('a job was cancelled; nothing to report')
        return
    fc = sha('SYNC_FORKGRAM_COMMIT')
    cand = sha('SYNC_CANDIDATE')
    if status == 'conflict':
        report(f'conflict {fc} {sha("SYNC_CONFLICT_COMMIT")}', body_conflict())
    elif results[0] != 'success':
        err = env('SYNC_ERROR') or 'unknown'
        report('error ' + hashlib.sha1(err.encode()).hexdigest()[:12], body_error())
    elif status == 'next-edited':
        report(f'next-edited {sha("SYNC_EXISTING_NEXT")} {sha("SYNC_FORKGRAM_TIP")}', body_next_edited())
    elif status == 'candidate' and results[1] == 'failure':
        report(f'compile {cand}', body_compile())
    elif status == 'candidate' and results[1] == 'success' and results[2] == 'failure':
        report(f'promote {cand}', body_promote())
    elif status == 'candidate' and results[2] == 'success':
        tag = env('PROMOTE_TAG')
        moved = f'the old tip is tagged `{tag}`' if re.match(r'^[0-9A-Za-z._-]+$', tag) else 'it already was the candidate'
        note = f'Done: `multigram` now carries Forkgram {version()} (`{short(cand)}`); {moved}. {run_line()}'.strip()
        if env('SYNC_DROPPED'):
            note += ('\n\nThese MultiGram commits are not on the new `multigram` (Forkgram already has '
                     'them, or `multigram-next` left them out with allow_drop):\n' + block(env('SYNC_DROPPED')))
        close(note)
    elif status == 'behind':
        if open_issue() is None:
            report('', body_behind())
        else:
            print('multigram is behind and an issue is already open; nothing to add')
    elif status == 'up-to-date':
        if open_issue() is not None:
            close(f'`multigram` is in step with Forkgram {version()} again. {run_line()}'.strip())
    else:
        print('nothing to report')


if __name__ == '__main__':
    main()
