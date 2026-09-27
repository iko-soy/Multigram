#!/usr/bin/env bash
# Throwaway check for work/rebrand-active only (never merged): inspect what the rebranded
# compile produced, using aapt2 from the runner's Android SDK.
set -u
fail=0
ok() { echo "ok   $*"; }
bad() { echo "FAIL $*"; fail=1; }
props=multigram/rebrand/rebrand.properties
id=$(sed -n 's/^REBRAND_APPLICATION_ID=//p' $props)
name=$(sed -n 's/^REBRAND_APP_NAME=//p' $props)
acct=$(sed -n 's/^REBRAND_ACCOUNT_TYPE=//p' $props)
read -r shape bg fg < <(sed -n 's/^REBRAND_ICON=//p' $props)
echo "expect id=$id name=$name account=$acct icon=$shape $bg $fg"
aapt2=$(ls -d "$ANDROID_HOME"/build-tools/*/ 2>/dev/null | sort -V | tail -1)aapt2
[ -x "$aapt2" ] || aapt2=$(find ~/.gradle -type f -name aapt2 2>/dev/null | head -1)
echo "aapt2=$aapt2"
apk=$(find TMessagesProj_App/build/intermediates -name '*.ap_' -path '*afatRelease*' | head -1)
echo "linked resources: $apk"
[ -n "$apk" ] || { bad "no linked resources for afatRelease"; exit 1; }

badging=$("$aapt2" dump badging "$apk" 2>&1)
echo "$badging" | grep -E "^(package|application-label):"
echo "$badging" | grep -q "^package: name='$id.beta'" && ok "package is $id.beta" || bad "package"
echo "$badging" | grep -q "^application-label:'$name'" && ok "label is $name" || bad "label"

res=$("$aapt2" dump resources "$apk" 2>&1)
for s in AppName AppNameBeta; do
  echo "$res" | grep -n -E "string/$s([^A-Za-z0-9_]|$)" | head -3
  line=$(echo "$res" | grep -A2 -E "string/$s([^A-Za-z0-9_]|$)" | head -3 | tr '\n' ' ')
  echo "$s: $line"
  v=$(echo "$line" | grep -o '"[^"]*"' | head -1)
  [ "$v" = "\"$name\"" ] && ok "$s = $v" || bad "$s = $v"
done
flag=$(echo "$res" | grep -A2 "bool/multigram_rebrand_active" | head -3 | tr '\n' ' ')
echo "flag: $flag"
echo "$flag" | grep -q "true" && ok "bool/multigram_rebrand_active is true" || bad "rebrand flag"

xt() { "$aapt2" dump xmltree --file "$1" "$apk" 2>&1; }
for f in res/xml/auth.xml res/xml/sync_contacts.xml; do
  t=$(xt $f | grep -i accountType)
  echo "$f: $t"
  echo "$t" | grep -q "\"$acct\"" && ok "$f account type $acct" || bad "$f account type"
done
menu=$(xt res/xml/auth_menu.xml | grep -i targetPackage)
echo "auth_menu.xml: $menu"
echo "$menu" | grep -q "\"$id.beta\"" && ok "auth_menu targetPackage $id.beta" || bad "auth_menu targetPackage"

for d in splash_fork_320 tg_splash_320; do
  p=$(echo "$res" | grep -A3 -E "drawable/$d[[:space:]]" | grep -o 'res/[^ ]*\.xml' | head -1)
  [ -n "$p" ] || p=res/drawable/$d.xml
  v=$(xt "$p")
  echo "$v" | grep -m1 -iE "fillColor" || true
  if echo "$v" | grep -qi "^N\?.*E: vector" && echo "$v" | grep -qi "$(echo ${bg#\#} | tr A-F a-f)" && ! echo "$v" | grep -qi "animated-vector"; then
    ok "$d is the generated vector ($p)"; else bad "$d ($p)"; echo "$v" | head -12; fi
done

# notification icon: compare the linked PNGs against the generated ones (aapt2 may recompress,
# so compare decoded alpha masks)
tmp=$(mktemp -d); (cd $tmp && unzip -q -o "$OLDPWD/$apk" 'res/drawable-*/notification.png' 2>/dev/null || true)
python3 - "$tmp" <<'PY'
import sys, zlib, struct, glob, os
def rgba(path):
    """(width, alpha list) of a non-interlaced PNG of any colour type, bit depth <= 8."""
    b = open(path, "rb").read(); i = 8; idat = b""; trns = b""
    while i + 8 <= len(b):
        ln = struct.unpack(">I", b[i:i+4])[0]; t = b[i+4:i+8]; d = b[i+8:i+8+ln]
        if t == b"IHDR": w, h, bd, ct, _, _, il = struct.unpack(">IIBBBBB", d)
        if t == b"tRNS": trns = d
        if t == b"IDAT": idat += d
        if t == b"IEND": break
        i += 12 + ln
    ch = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ct]
    if il or bd > 8: return None
    bits = bd * ch; bpp = max(1, bits // 8); stride = (w * bits + 7) // 8
    raw = zlib.decompress(idat); rows = []; prev = bytearray(stride); p = 0
    for y in range(h):
        ft = raw[p]; p += 1; line = bytearray(raw[p:p+stride]); p += stride
        for x in range(stride):
            a = line[x-bpp] if x >= bpp else 0; c = prev[x-bpp] if x >= bpp else 0; up = prev[x]
            if ft == 1: line[x] = (line[x] + a) & 255
            elif ft == 2: line[x] = (line[x] + up) & 255
            elif ft == 3: line[x] = (line[x] + (a + up) // 2) & 255
            elif ft == 4:
                pp = a + up - c; pa, pb, pc = abs(pp-a), abs(pp-up), abs(pp-c)
                line[x] = (line[x] + (a if pa <= pb and pa <= pc else up if pb <= pc else c)) & 255
        rows.append(bytes(line)); prev = line
    alpha = []
    for row in rows:
        for x in range(w):
            if bd == 8:
                px = row[x*ch:(x+1)*ch]
            else:
                pos = x * bd; px = [(row[pos // 8] >> (8 - bd - pos % 8)) & ((1 << bd) - 1)]
            if ct == 6: alpha.append(px[3])
            elif ct == 4: alpha.append(px[1])
            elif ct == 3: alpha.append(trns[px[0]] if px[0] < len(trns) else 255)
            else: alpha.append(255)
    return w, alpha
bad = 0; n = 0
for f in sorted(glob.glob(os.path.join(sys.argv[1], "res/drawable-*/notification.png"))):
    dens = os.path.basename(os.path.dirname(f)).split("-")[1]
    gen = "multigram/rebrand/generated/res/drawable-%s/notification.png" % dens
    a, b = rgba(f), rgba(gen)
    same = a is not None and b is not None and a[0] == b[0] and max(abs(x - y) for x, y in zip(a[1], b[1])) <= 2
    print("%s  notification %s vs generated: %s" % ("ok  " if same else "FAIL", f.split("res/")[1], "same mask" if same else "differs"))
    bad += not same; n += 1
if n == 0: print("FAIL no notification PNGs in the linked resources"); bad = 1
sys.exit(1 if bad else 0)
PY
[ $? -eq 0 ] || fail=1

loc=$(find TMessagesProj_App/build/generated/telegramStrings -name localization_en.bin -path '*afatRelease*' | head -1)
if [ -n "$loc" ] && grep -qa "$name" "$loc"; then ok "bundled en strings carry $name"; else bad "bundled strings ($loc)"; fi
gen=$(find TMessagesProj_App/build/generated/multigramRebrand -name auth_menu.xml | sort)
echo "generated auth menus:"; for f in $gen; do echo "  $f: $(grep -o 'targetPackage="[^"]*"' $f)"; done
exit $fail
