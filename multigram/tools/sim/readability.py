"""Readability suite on top of the ported colour engine.

A pair is (fg, bg): fg is a colour key read with Theme.getColor(); bg is a colour key or one of the
derived surfaces below.  Contrast is WCAG 2.2 (relative luminance from the exact 8-bit sRGB table),
after compositing any translucent colour over what is under it (src-over in gamma-encoded sRGB, as
Android's legacy 8888 pipeline does).  Gradient surfaces are sampled (stops, midpoints, centroid) and
the minimum contrast over the samples is reported.

Derived surfaces
  @in_bubble      chat_inBubble (composited over the wallpaper samples when translucent)
  @out_bubble     chat_outBubble, or its gradient when currentColors has chat_outBubbleGradient1:
                  linear top-to-bottom gradient {g3, g2, g1, outBubble} (MessageDrawable.setTop) or,
                  with >= 3 colours and the animated flag, the 4-point MotionBackgroundDrawable.
  @wallpaper      what createBackgroundDrawable() shows for this accent: motion gradient (pattern
                  intensity >= 0: the gradient; < 0: black, gradient only inside pattern strokes),
                  two-colour BackgroundGradientDrawable, ColorDrawable, or the built-in 'd' wallpaper.
  @service        service-message pill on a device with the default "chat background" lite-mode
                  flag: gradient wallpapers -> the gradient bitmap through the ColorMatrix of
                  applyChatServiceMessageColor() with WHITE text; otherwise chat_serviceBackground
                  (or calcDrawableColor) over the wallpaper with chat_serviceText.
  @service_lite   same pill when the gradient service shader is off (LiteMode chat background off or
                  PERFORMANCE_CLASS_LOW): chat_serviceBackground / calcDrawableColor + chat_serviceText.
"""
import engine as E
import detmath as D

TEXT = 4.5          # WCAG 2.2 SC 1.4.3, normal-size text
NONTEXT = 3.0       # WCAG 2.2 SC 1.4.11 (UI components / graphical objects), SC 1.4.3 large text
SEPARATION = 1.15   # bubble vs wallpaper: not a WCAG criterion; see PAIRS doc


def P(name, fg, bg, thr, why):
    return {"name": name, "fg": fg, "bg": bg, "threshold": thr, "why": why}


PAIRS = [
    # --- settings / list surfaces -------------------------------------------------------
    P("list_text", "windowBackgroundWhiteBlackText", "windowBackgroundWhite", TEXT, "primary 16sp list/settings text"),
    P("list_gray_text", "windowBackgroundWhiteGrayText", "windowBackgroundWhite", TEXT, "secondary 13-14sp text (last seen, descriptions)"),
    P("list_gray_text2", "windowBackgroundWhiteGrayText2", "windowBackgroundWhite", TEXT, "secondary/value text in cells"),
    P("list_accent_text", "windowBackgroundWhiteBlueText", "windowBackgroundWhite", TEXT, "accent text (online status, highlighted values), normal size"),
    P("list_accent_text2", "windowBackgroundWhiteBlueText2", "windowBackgroundWhite", TEXT, "accent text variant used in cells"),
    P("list_accent_text4", "windowBackgroundWhiteBlueText4", "windowBackgroundWhite", TEXT, "accent text-buttons in lists (e.g. 'Add account')"),
    P("list_section_header", "windowBackgroundWhiteBlueHeader", "windowBackgroundWhite", TEXT, "section headers are 15sp medium: not WCAG 'large'"),
    P("list_accent_button", "windowBackgroundWhiteBlueButton", "windowBackgroundWhite", TEXT, "text buttons in settings cells"),
    P("list_accent_icon", "windowBackgroundWhiteBlueIcon", "windowBackgroundWhite", NONTEXT, "accent icons: graphical object"),
    P("list_link", "windowBackgroundWhiteLinkText", "windowBackgroundWhite", TEXT, "links inside settings text"),
    P("list_value", "windowBackgroundWhiteValueText", "windowBackgroundWhite", TEXT, "right-aligned values in settings"),
    P("input_focus_line", "windowBackgroundWhiteInputFieldActivated", "windowBackgroundWhite", NONTEXT, "focused input underline: state indicator"),
    P("switch_on", "switchTrackChecked", "windowBackgroundWhite", NONTEXT, "switch ON state must be perceivable"),
    P("checkbox_on", "checkboxSquareBackground", "windowBackgroundWhite", NONTEXT, "checked checkbox fill vs page"),
    P("checkbox_mark", "checkboxSquareCheck", "checkboxSquareBackground", NONTEXT, "check mark glyph on the fill"),
    P("radio_on", "radioBackgroundChecked", "windowBackgroundWhite", NONTEXT, "selected radio button"),
    P("profile_tab_selected", "profile_tabSelectedText", "windowBackgroundWhite", TEXT, "profile shared-media tab label"),
    # --- dialogs ---------------------------------------------------------------------------
    P("dialog_text", "dialogTextBlack", "dialogBackground", TEXT, "dialog body text"),
    P("dialog_accent_text", "dialogTextBlue", "dialogBackground", TEXT, "accent text in dialogs"),
    P("dialog_link", "dialogTextLink", "dialogBackground", TEXT, "links in dialogs"),
    P("dialog_button", "dialogButton", "dialogBackground", TEXT, "OK/Cancel labels are 14sp medium: normal text"),
    P("dialog_checkbox", "dialogRoundCheckBox", "dialogBackground", NONTEXT, "selected round checkbox in dialogs"),
    P("dialog_checkbox_mark", "dialogRoundCheckBoxCheck", "dialogRoundCheckBox", NONTEXT, "check glyph on it"),
    # --- chat list ------------------------------------------------------------------------
    P("chats_name", "chats_name", "windowBackgroundWhite", TEXT, "chat title in the list"),
    P("chats_preview", "chats_message", "windowBackgroundWhite", TEXT, "message preview"),
    P("chats_preview_sender", "chats_nameMessage", "windowBackgroundWhite", TEXT, "sender name in group previews (accent)"),
    P("chats_preview_action", "chats_actionMessage", "windowBackgroundWhite", TEXT, "typing.../media label (accent)"),
    P("chats_date", "chats_date", "windowBackgroundWhite", TEXT, "time/date in the list"),
    P("unread_badge_text", "chats_unreadCounterText", "chats_unreadCounter", TEXT, "13sp bold digits: below the 14pt-bold 'large' limit"),
    P("unread_badge", "chats_unreadCounter", "windowBackgroundWhite", NONTEXT, "badge must stand out from the row"),
    P("read_checks", "chats_sentReadCheck", "windowBackgroundWhite", NONTEXT, "read-status icon"),
    P("fab_icon", "chats_actionIcon", "chats_actionBackground", NONTEXT, "pencil icon on the floating action button"),
    P("fab", "chats_actionBackground", "windowBackgroundWhite", NONTEXT, "floating action button vs list"),
    P("folder_tab_active", "actionBarTabActiveText", "actionBarDefault", TEXT, "selected folder tab label (sits on the action bar)"),
    P("folder_tab_line", "actionBarTabLine", "actionBarDefault", NONTEXT, "selected folder tab indicator"),
    # --- action bar -----------------------------------------------------------------------
    P("actionbar_title", "actionBarDefaultTitle", "actionBarDefault", TEXT, "18sp medium title: not WCAG 'large' (needs 18.66px bold or 24px)"),
    P("actionbar_icons", "actionBarDefaultIcon", "actionBarDefault", NONTEXT, "back/menu icons"),
    P("actionbar_subtitle", "actionBarDefaultSubtitle", "actionBarDefault", TEXT, "subtitle text"),
    P("chat_header_status", "chat_status", "actionBarDefault", TEXT, "'online'/'typing' in the chat header (accent)"),
    # --- incoming bubble --------------------------------------------------------------------
    P("in_text", "chat_messageTextIn", "@in_bubble", TEXT, "message body"),
    P("in_link", "chat_messageLinkIn", "@in_bubble", TEXT, "links (accent)"),
    P("in_time", "chat_inTimeText", "@in_bubble", TEXT, "12sp time stamp"),
    P("in_reply_name", "chat_inReplyNameText", "@in_bubble", TEXT, "reply header name (accent)"),
    P("in_reply_text", "chat_inReplyMessageText", "@in_bubble", TEXT, "quoted reply text"),
    P("in_forward_name", "chat_inForwardedNameText", "@in_bubble", TEXT, "'Forwarded from' name (accent)"),
    P("in_site_name", "chat_inSiteNameText", "@in_bubble", TEXT, "link-preview site name (accent)"),
    P("in_file_info", "chat_inFileInfoText", "@in_bubble", TEXT, "file size / duration"),
    P("in_instant_button", "chat_inPreviewInstantText", "@in_bubble", TEXT, "Instant View button label (accent)"),
    P("in_reply_line", "chat_inReplyLine", "@in_bubble", NONTEXT, "reply bar (accent)"),
    P("in_media_button", "chat_inLoader", "@in_bubble", NONTEXT, "file/voice play button (accent)"),
    P("in_voice_progress", "chat_inVoiceSeekbarFill", "@in_bubble", NONTEXT, "voice-message waveform progress (accent)"),
    # --- outgoing bubble --------------------------------------------------------------------
    P("out_text", "chat_messageTextOut", "@out_bubble", TEXT, "message body (every gradient sample)"),
    P("out_link", "chat_messageLinkOut", "@out_bubble", TEXT, "links"),
    P("out_time", "chat_outTimeText", "@out_bubble", TEXT, "12sp time stamp"),
    P("out_read_check", "chat_outSentCheckRead", "@out_bubble", NONTEXT, "read-status checks"),
    P("out_reply_name", "chat_outReplyNameText", "@out_bubble", TEXT, "reply header name"),
    P("out_reply_text", "chat_outReplyMessageText", "@out_bubble", TEXT, "quoted reply text"),
    P("out_forward_name", "chat_outForwardedNameText", "@out_bubble", TEXT, "'Forwarded from' name"),
    P("out_site_name", "chat_outSiteNameText", "@out_bubble", TEXT, "link-preview site name"),
    P("out_file_info", "chat_outFileInfoText", "@out_bubble", TEXT, "file size / duration (subTextColor in gradient mode)"),
    P("out_instant_button", "chat_outPreviewInstantText", "@out_bubble", TEXT, "Instant View button label"),
    P("out_reply_line", "chat_outReplyLine", "@out_bubble", NONTEXT, "reply bar"),
    P("out_media_button", "chat_outLoader", "@out_bubble", NONTEXT, "file/voice play button"),
    P("out_voice_progress", "chat_outVoiceSeekbarFill", "@out_bubble", NONTEXT, "voice waveform progress"),
    # --- composer / panels -----------------------------------------------------------------
    P("composer_text", "chat_messagePanelText", "chat_messagePanelBackground", TEXT, "typed text"),
    P("composer_hint", "chat_messagePanelHint", "chat_messagePanelBackground", TEXT, "placeholder text (WCAG applies to placeholders)"),
    P("composer_send", "chat_messagePanelSend", "chat_messagePanelBackground", NONTEXT, "send button icon (accent)"),
    P("composer_icons", "chat_messagePanelIcons", "chat_messagePanelBackground", NONTEXT, "attach/emoji icons"),
    P("reply_panel_name", "chat_replyPanelName", "chat_messagePanelBackground", TEXT, "'Reply to X' name above the composer (accent)"),
    P("pinned_title", "chat_topPanelTitle", "chat_topPanelBackground", TEXT, "pinned-message bar title (accent)"),
    P("filled_button_text", "featuredStickers_buttonText", "featuredStickers_addButton", TEXT, "label of accent-filled buttons (Join, Add, Start)"),
    # --- added by sim-verify: frequently read pairs missing from the original 75 -------------
    P("settings_footnote", "windowBackgroundWhiteGrayText4", "windowBackgroundGray", TEXT, "TextInfoPrivacyCell footnotes on the grey settings background"),
    P("chats_attach_label", "chats_attachMessage", "windowBackgroundWhite", TEXT, "'Photo'/'Voice message' label in chat-list previews (accent)"),
    P("chats_muted_badge_text", "chats_unreadCounterText", "chats_unreadCounterMuted", TEXT, "digits on muted-chat unread badges"),
    P("popup_menu_item", "actionBarDefaultSubmenuItem", "actionBarDefaultSubmenuBackground", TEXT, "popup/overflow menu items"),
    P("pinned_text", "chat_topPanelMessage", "chat_topPanelBackground", TEXT, "pinned-message bar text"),
    P("go_down_counter", "chat_goDownButtonCounter", "chat_goDownButtonCounterBackground", TEXT, "unread counter on the scroll-down button (accent fill)"),
    P("list_accent_text3", "windowBackgroundWhiteBlueText3", "windowBackgroundWhite", TEXT, "accent text variant"),
    P("list_accent_text5", "windowBackgroundWhiteBlueText5", "windowBackgroundWhite", TEXT, "accent text variant"),
    P("list_accent_text6", "windowBackgroundWhiteBlueText6", "windowBackgroundWhite", TEXT, "accent text variant"),
    P("list_accent_text7", "windowBackgroundWhiteBlueText7", "windowBackgroundWhite", TEXT, "accent text variant"),
    P("dialog_accent_text2", "dialogTextBlue2", "dialogBackground", TEXT, "accent text in dialogs"),
    P("dialog_accent_text4", "dialogTextBlue4", "dialogBackground", TEXT, "accent text in dialogs"),
    P("in_file_name", "chat_inFileNameText", "@in_bubble", TEXT, "file name in incoming documents (accent)"),
    P("in_via_bot", "chat_inViaBotNameText", "@in_bubble", TEXT, "'via @bot' (accent)"),
    P("in_views", "chat_inViews", "@in_bubble", TEXT, "channel view counter"),
    P("out_file_name", "chat_outFileNameText", "@out_bubble", TEXT, "file name in outgoing documents"),
    P("out_views", "chat_outViews", "@out_bubble", TEXT, "view counter in outgoing channel posts"),
    P("out_audio_duration", "chat_outAudioDurationText", "@out_bubble", TEXT, "audio duration (subTextColor)"),
    # --- added by canvas-fix: content drawn on accent fills (the on-accent rule's other keys) ---------
    P("dialog_checkbox_square_mark", "dialogCheckboxSquareCheck", "dialogCheckboxSquareBackground", NONTEXT, "CheckBoxSquare(isAlert) mark (CheckBoxSquare.java:59)"),
    P("attach_checkbox_mark", "chat_attachCheckBoxCheck", "chat_attachCheckBoxBackground", NONTEXT, "photo-picker selection check (PhotoAttachPhotoCell.java:276)"),
    P("in_media_icon", "chat_inMediaIcon", "chat_inLoader", NONTEXT, "play/download glyph on the incoming loader circle (ChatMessageCell.java:15057)"),
    P("in_contact_icon", "chat_inContactIcon", "chat_inContactBackground", NONTEXT, "contact glyph on its circle (Theme.java:8533-8534)"),
    P("picker_badge_text", "picker_badgeText", "picker_badge", TEXT, "count on the picker Done badge (PickerBottomLayout.java:66)"),
    P("dialog_fab_icon", "dialogFloatingIcon", "dialogFloatingButton", NONTEXT, "floating send button glyph in share/caption sheets"),
    # --- wallpaper & service messages --------------------------------------------------------
    P("service_text", "chat_serviceText", "@service", TEXT, "date headers / service messages (14sp); WHITE is used instead of chat_serviceText when the gradient service shader is active"),
    P("service_text_lite", "chat_serviceText", "@service_lite", TEXT, "same, gradient service shader off (lite mode / low-end devices)"),
    P("in_bubble_vs_wallpaper", "chat_inBubble", "@wallpaper", SEPARATION, "bubble shape must separate from the wallpaper (1.15:1, min over wallpaper samples)"),
    P("out_bubble_vs_wallpaper", "chat_outBubble", "@wallpaper", SEPARATION, "outgoing bubble (all gradient samples) vs wallpaper samples"),
]

PAIR_INDEX = {p["name"]: i for i, p in enumerate(PAIRS)}


def check_keys(model):
    """Every key named by the suite must exist in Theme.java."""
    missing = []
    for p in PAIRS:
        for k in (p["fg"], p["bg"]):
            if not k.startswith("@") and ("key_" + k) not in model.K:
                missing.append(k)
    return missing


# ------------------------------------------------------------------------------------------
# colour helpers (gamma-space, 8-bit)
# ------------------------------------------------------------------------------------------

def rgb(c):
    return c & 0xFFFFFF


def over(fg, bg):
    """src-over of an ARGB colour on an opaque background (8-bit, rounded)."""
    a = (fg >> 24) & 0xFF
    if a == 255:
        return fg & 0xFFFFFF
    if a == 0:
        return bg & 0xFFFFFF
    ia = 255 - a
    r = (((fg >> 16) & 0xFF) * a + ((bg >> 16) & 0xFF) * ia + 127) // 255
    g = (((fg >> 8) & 0xFF) * a + ((bg >> 8) & 0xFF) * ia + 127) // 255
    b = ((fg & 0xFF) * a + (bg & 0xFF) * ia + 127) // 255
    return (r << 16) | (g << 8) | b


def mix(c1, c2):
    return ((((c1 >> 16) & 0xFF) + ((c2 >> 16) & 0xFF) + 1) // 2 << 16) | \
           ((((c1 >> 8) & 0xFF) + ((c2 >> 8) & 0xFF) + 1) // 2 << 8) | \
           (((c1 & 0xFF) + (c2 & 0xFF) + 1) // 2)


def centroid(cs):
    n = len(cs)
    r = sum((c >> 16) & 0xFF for c in cs)
    g = sum((c >> 8) & 0xFF for c in cs)
    b = sum(c & 0xFF for c in cs)
    return (((r + n // 2) // n) << 16) | (((g + n // 2) // n) << 8) | ((b + n // 2) // n)


def samples_motion(cs):
    """4-point (or 3-point) MotionBackgroundDrawable gradient: corners, pairwise midpoints, centroid."""
    cs = [c & 0xFFFFFF for c in cs]
    out = list(cs)
    for i in range(len(cs)):
        for j in range(i + 1, len(cs)):
            out.append(mix(cs[i], cs[j]))
    out.append(centroid(cs))
    return _uniq(out)


def samples_linear(cs):
    cs = [c & 0xFFFFFF for c in cs]
    out = list(cs)
    for i in range(len(cs) - 1):
        out.append(mix(cs[i], cs[i + 1]))
    return _uniq(out)


def _uniq(xs):
    seen = set()
    out = []
    for x in xs:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


# ------------------------------------------------------------------------------------------
# wallpaper + service pill model
# ------------------------------------------------------------------------------------------

BLACK = 0x000000
WHITE = 0xFFFFFF


def _java_hsv_double(c):
    """AndroidUtilities.rgbToHsv (double)."""
    rf, gf, bf = ((c >> 16) & 0xFF) / 255.0, ((c >> 8) & 0xFF) / 255.0, (c & 0xFF) / 255.0
    mx = rf if (rf > gf and rf > bf) else max(gf, bf)
    mn = rf if (rf < gf and rf < bf) else min(gf, bf)
    d = mx - mn
    s = 0 if mx == 0 else d / mx
    if mx == mn:
        h = 0.0
    else:
        if rf > gf and rf > bf:
            h = (gf - bf) / d + (6 if gf < bf else 0)
        elif gf > bf:
            h = (bf - rf) / d + 2
        else:
            h = (rf - gf) / d + 4
        h /= 6
    return h, s, mx


def _java_hsv_to_rgb(h, s, v):
    """AndroidUtilities.hsvToRgb (double, truncating)."""
    import math
    i = float(int(math.floor(h * 6)))
    f = h * 6 - i
    p = v * (1 - s)
    q = v * (1 - f * s)
    t = v * (1 - (1 - f) * s)
    k = int(i) % 6
    r, g, b = [(v, t, p), (q, v, p), (p, v, t), (p, q, v), (t, p, v), (v, p, q)][k]
    return int(r * 255), int(g * 255), int(b * 255)


def calc_drawable_color(kind, colors):
    """AndroidUtilities.calcDrawableColor(drawable)[0] (serviceMessageColor)."""
    if kind == "motion":
        return 0x2D000000
    if kind == "gradient":
        bc = E.average_color(colors[0], colors[1])
    else:
        bc = colors[0]
    h, s, v = _java_hsv_double(bc)
    s = min(1.0, s + 0.05 + 0.1 * (1.0 - s))
    v = max(0, v * 0.65)
    r, g, b = _java_hsv_to_rgb(h, s, v)
    return (0x66 << 24) | (r << 16) | (g << 8) | b


def service_matrix(model, is_dark, intensity):
    sm = model.parsed["theme_java"]["service_matrix"]
    br = sm["intensity_ge0"] if intensity >= 0 else sm["intensity_lt0"]
    sat = E.f32(br["sat"])
    mult = E.f32(br["mult_dark"] if is_dark else br["mult_light"])
    add = E.f32(E.f32(br["add_dark"] if is_dark else br["add_light"]) * 255.0)
    inv = E.f32(1.0 - sat)
    R, G, B = E.f32(E.f32(0.213) * inv), E.f32(E.f32(0.715) * inv), E.f32(E.f32(0.072) * inv)
    rows = [(R + sat, G, B), (R, G + sat, B), (R, G, B + sat)]
    return [(mult * a, mult * b, mult * c, add) for a, b, c in rows]


def apply_matrix(mat, c):
    r, g, b = (c >> 16) & 0xFF, (c >> 8) & 0xFF, c & 0xFF
    out = []
    for a, bb, cc, t in mat:
        v = a * r + bb * g + cc * b + t
        v = 0 if v < 0 else (255 if v > 255 else v)
        out.append(int(v + 0.5))
    return (out[0] << 16) | (out[1] << 8) | out[2]


def entry(pal, name):
    """(present, value) of a key in currentColors."""
    k = pal.model.K[name]
    if isinstance(pal, E.LazyPalette):
        return pal.cur_entry(k)
    return (k in pal.colors, pal.colors.get(k, 0))


class Wallpaper:
    __slots__ = ("kind", "colors", "intensity", "pattern", "rotation", "fill", "gradient", "source",
                 "service", "service_text", "service_lite", "service_lite_text", "shader")


def wallpaper_model(pal):
    """Theme.loadWallpaper()/createBackgroundDrawable() for a theme+accent with no override wallpaper,
    plus applyChatServiceMessageColor()."""
    th, m, acc = pal.theme, pal.model, pal.accent
    w = Wallpaper()
    default_theme = th.firstAccentIsDefault and pal.current_id == m.DEFAULT_ACCENT_ID
    bg = 0 if default_theme else pal.raw("chat_wallpaper")
    g1 = pal.raw("chat_wallpaper_gradient_to1")
    g2 = pal.raw("chat_wallpaper_gradient_to2")
    g3 = pal.raw("chat_wallpaper_gradient_to3")
    rot_present, rot = entry(pal, "key_chat_wallpaper_gradient_rotation")
    w.rotation = rot if rot_present else 45
    # (int) (accent.patternIntensity * 100): float multiply, truncation
    w.intensity = E.f2i(E.f32(acc.patternIntensity * 100.0))
    has_pattern_file = bool(acc.patternSlug)          # ThemeAccent.getPathToWallpaper() != null
    if bg != 0:
        w.source = "accent/theme colours"
        if g1 != 0 and g2 != 0:
            w.kind, w.colors, w.pattern = "motion", [bg, g1, g2, g3], has_pattern_file
        elif g1 == 0 or g1 == bg:
            w.kind, w.colors, w.pattern = "color", [bg], False
        else:
            w.kind, w.colors, w.pattern = "gradient", [bg, g1], False
    else:
        dw = m.parsed["theme_java"]["default_wallpaper"]
        w.source = "createDefaultWallpaper()"
        w.kind, w.colors, w.pattern, w.intensity = "motion", list(dw["colors"]), True, dw["intensity"]
    cs = [c for c in w.colors if c != 0]
    if w.kind == "motion":
        w.gradient = samples_motion(cs)
        if w.intensity < 0:
            w.fill = [BLACK]            # black; the gradient only shows through pattern strokes
        else:
            w.fill = w.gradient
    elif w.kind == "gradient":
        w.gradient = samples_linear(cs)
        w.fill = w.gradient
    else:
        w.gradient = [cs[0] & 0xFFFFFF]
        w.fill = w.gradient
    # --- service pills ----------------------------------------------------------------------
    K = m.K
    present, sb = entry(pal, "key_chat_serviceBackground")
    pill_color = sb if present else calc_drawable_color(w.kind, cs)
    lite = [over(pill_color, f) for f in w.fill]
    lite_text = pal.get("chat_serviceText")
    w.service_lite, w.service_lite_text = lite, lite_text
    if w.kind == "motion":
        w.shader = True
        mat = service_matrix(m, th.is_dark, w.intensity)
        w.service = _uniq([apply_matrix(mat, c) for c in w.gradient])
        w.service_text = E.s32(0xFFFFFFFF)
    else:
        w.shader = False
        w.service, w.service_text = lite, lite_text
    return w


# ------------------------------------------------------------------------------------------
# evaluation
# ------------------------------------------------------------------------------------------

def out_bubble_samples(pal):
    """Colours behind outgoing-message text.  Solid: getColor(chat_outBubble) (ARGB, may be translucent);
    gradient: opaque RGB samples of the shader MessageDrawable.setTop() builds."""
    base = pal.get("chat_outBubble")
    g1 = pal.raw("chat_outBubbleGradient1")
    if g1 == 0:
        return [base], "solid"
    g2 = pal.raw("chat_outBubbleGradient2")
    g3 = pal.raw("chat_outBubbleGradient3")
    animated = pal.raw("chat_outBubbleGradientAnimated") != 0
    if g2 != 0 and animated:
        return samples_motion([base, g1, g2] + ([g3] if g3 != 0 else [])), "motion"
    if g2 != 0:
        stops = [g3, g2, g1, base] if g3 != 0 else [g2, g1, base]
    else:
        stops = [g1, base]
    return samples_linear(stops), "linear"


class Evaluator:
    """Computes every pair's contrast for one palette (lazily, memoised)."""

    def __init__(self, pal):
        self.pal = pal
        self._wp = None
        self._in = None
        self._out = None
        self._surf = {}

    @property
    def wp(self):
        if self._wp is None:
            self._wp = wallpaper_model(self.pal)
        return self._wp

    def surface(self, bg):
        s = self._surf.get(bg)
        if s is not None:
            return s
        pal = self.pal
        if bg == "@wallpaper":
            s = self.wp.fill
        elif bg == "@in_bubble":
            c = pal.get("chat_inBubble")
            s = [c & 0xFFFFFF] if ((c >> 24) & 0xFF) == 255 else _uniq([over(c, f) for f in self.wp.fill])
        elif bg == "@out_bubble":
            cs, mode = out_bubble_samples(pal)
            if mode != "solid" or ((cs[0] >> 24) & 0xFF) == 255:
                s = [c & 0xFFFFFF for c in cs]
            else:
                s = _uniq([over(cs[0], f) for f in self.wp.fill])
        elif bg == "@service":
            s = self.wp.service
        elif bg == "@service_lite":
            s = self.wp.service_lite
        else:
            c = pal.get(bg)
            if ((c >> 24) & 0xFF) != 255:
                c = over(c, pal.get("windowBackgroundWhite"))
            s = [c & 0xFFFFFF]
        self._surf[bg] = s
        return s

    def contrast(self, i):
        p = PAIRS[i]
        bg = p["bg"]
        if bg == "@wallpaper":
            # separation: bubble (all its samples, composited on the wallpaper) vs wallpaper samples
            bub = self.surface("@in_bubble" if p["fg"] == "chat_inBubble" else "@out_bubble")
            best = 1e9
            for f in self.wp.fill:
                for b in bub:
                    c = D.contrast(b, f)
                    if c < best:
                        best = c
            return best
        if bg == "@service":
            fg = self.wp.service_text
        elif bg == "@service_lite":
            fg = self.wp.service_lite_text
        else:
            fg = self.pal.get(p["fg"])
        best = 1e9
        for s in self.surface(bg):
            c = D.contrast(over(fg, s), s)
            if c < best:
                best = c
        return best

    def all(self, idx=None):
        if idx is None:
            idx = range(len(PAIRS))
        return {i: self.contrast(i) for i in idx}


# ------------------------------------------------------------------------------------------
# baseline
# ------------------------------------------------------------------------------------------

_BASELINE = {}


def stock_palette(theme):
    acc = theme.stock_accent()
    return E.palette(theme, acc, acc.id)


def baseline(theme):
    key = (theme.model.tag, theme.name)
    b = _BASELINE.get(key)
    if b is None:
        ev = Evaluator(stock_palette(theme))
        b = ev.all()
        _BASELINE[key] = b
    return b


def effective_thresholds(theme):
    """Pass rule: contrast >= threshold OR contrast >= the stock contrast of that pair on this theme."""
    b = baseline(theme)
    return [min(PAIRS[i]["threshold"], b[i]) for i in range(len(PAIRS))]
