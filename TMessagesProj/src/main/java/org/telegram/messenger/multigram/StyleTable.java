package org.telegram.messenger.multigram;

import android.content.Context;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.lang.ref.SoftReference;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.zip.CRC32;

/**
 * Reader for the bundled style table, assets/multigram_styles.bin (format version 1, documented in
 * multigram/tools/README.md and produced by multigram/tools/make_style_table.py).
 *
 * Every entry is a complete, pre-validated style for one bundled base theme: accent, outgoing-bubble colours
 * and a 2-4 colour wallpaper gradient without a pattern. The table was validated on top of the palette fix,
 * so an entry must be applied as a runtime accent ({@link PaletteFix#isRuntimeAccent}).
 *
 * This class only parses bytes; it never touches Theme, so it is safe to use before Theme is initialised.
 */
public final class StyleTable {

    public static final String ASSET_NAME = "multigram_styles.bin";

    private static final int MAGIC = 0x4D475354; // "MGST"
    private static final int VERSION = 1;
    private static final int HEADER_SIZE = 24;
    private static final int DIR_ENTRY_SIZE = 32;
    private static final int RECORD_SIZE = 40;
    private static final int THEME_KEY_BYTES = 20;
    private static final int DIR_FLAG_NIGHT = 0x01;

    public static final int FLAG_ANIMATED = 0x01;
    public static final int FLAG_MOTION = 0x02;

    /** One style. Colours are ARGB; 0 marks an unused slot. */
    public static final class Entry {
        public final String themeKey;
        public final boolean night;
        public final int accent;
        public final int bubble;
        public final int bubbleGradient1;
        public final int bubbleGradient2;
        public final int bubbleGradient3;
        public final int wallpaper1;
        public final int wallpaper2;
        public final int wallpaper3;
        public final int wallpaper4;
        public final int rotation;
        public final int flags;

        Entry(String themeKey, boolean night, ByteBuffer buf, int offset) {
            this.themeKey = themeKey;
            this.night = night;
            accent = buf.getInt(offset);
            bubble = buf.getInt(offset + 4);
            bubbleGradient1 = buf.getInt(offset + 8);
            bubbleGradient2 = buf.getInt(offset + 12);
            bubbleGradient3 = buf.getInt(offset + 16);
            wallpaper1 = buf.getInt(offset + 20);
            wallpaper2 = buf.getInt(offset + 24);
            wallpaper3 = buf.getInt(offset + 28);
            wallpaper4 = buf.getInt(offset + 32);
            rotation = buf.getShort(offset + 36) & 0xffff;
            flags = buf.get(offset + 38) & 0xff;
        }

        public boolean isAnimated() {
            return (flags & FLAG_ANIMATED) != 0;
        }

        public boolean isMotion() {
            return (flags & FLAG_MOTION) != 0;
        }

        /** The format's invariants (see multigram/tools/README.md). */
        boolean isValid() {
            if (themeKey == null || themeKey.isEmpty()) {
                return false;
            }
            if (!opaque(accent) || !opaque(bubble) || !opaque(bubbleGradient1) || !opaque(wallpaper1) || !opaque(wallpaper2)) {
                return false;
            }
            if (!unusedOrOpaque(bubbleGradient2) || !unusedOrOpaque(bubbleGradient3) || !unusedOrOpaque(wallpaper3) || !unusedOrOpaque(wallpaper4)) {
                return false;
            }
            if (bubbleGradient2 == 0 && bubbleGradient3 != 0 || wallpaper3 == 0 && wallpaper4 != 0) {
                return false;
            }
            if (isAnimated() && bubbleGradient2 == 0) {
                return false;
            }
            return rotation % 45 == 0 && rotation < 360 && (flags & ~(FLAG_ANIMATED | FLAG_MOTION)) == 0;
        }

        /** The 40-byte record as 80 hex digits, for storage in preferences. */
        public String toHex() {
            ByteBuffer b = ByteBuffer.allocate(RECORD_SIZE);
            b.putInt(accent).putInt(bubble).putInt(bubbleGradient1).putInt(bubbleGradient2).putInt(bubbleGradient3);
            b.putInt(wallpaper1).putInt(wallpaper2).putInt(wallpaper3).putInt(wallpaper4);
            b.putShort((short) rotation).put((byte) flags).put((byte) 0);
            StringBuilder sb = new StringBuilder(RECORD_SIZE * 2);
            for (byte v : b.array()) {
                sb.append(String.format(Locale.US, "%02x", v & 0xff));
            }
            return sb.toString();
        }

        /** Parses {@link #toHex()} output; returns null when it is malformed or breaks the format's rules. */
        public static Entry fromHex(String themeKey, boolean night, String hex) {
            if (hex == null || hex.length() != RECORD_SIZE * 2) {
                return null;
            }
            byte[] bytes = new byte[RECORD_SIZE];
            for (int i = 0; i < RECORD_SIZE; i++) {
                int hi = Character.digit(hex.charAt(2 * i), 16);
                int lo = Character.digit(hex.charAt(2 * i + 1), 16);
                if (hi < 0 || lo < 0) {
                    return null;
                }
                bytes[i] = (byte) (hi << 4 | lo);
            }
            Entry e = new Entry(themeKey, night, ByteBuffer.wrap(bytes), 0);
            return e.isValid() ? e : null;
        }

        private static boolean opaque(int color) {
            return (color >>> 24) == 0xff;
        }

        private static boolean unusedOrOpaque(int color) {
            return color == 0 || opaque(color);
        }
    }

    /** The last table loaded; kept softly, so Shuffle does not re-read and re-check the asset on the UI thread. */
    private static volatile SoftReference<StyleTable> cache;

    private final ByteBuffer data;
    private final int crc;
    private final int themeCount;
    private final String[] themeKeys;
    private final boolean[] themeNight;
    private final int[] themeFirst;
    private final int[] themeRecords;
    private final int dayCount;
    private final int nightCount;

    private StyleTable(ByteBuffer data, int crc, String[] keys, boolean[] night, int[] first, int[] count) {
        this.data = data;
        this.crc = crc;
        this.themeCount = keys.length;
        this.themeKeys = keys;
        this.themeNight = night;
        this.themeFirst = first;
        this.themeRecords = count;
        int d = 0, n = 0;
        for (int i = 0; i < themeCount; i++) {
            if (night[i]) {
                n += count[i];
            } else {
                d += count[i];
            }
        }
        dayCount = d;
        nightCount = n;
    }

    /** The table's CRC-32 (header field); it also fingerprints the table's contents. */
    public int getCrc() {
        return crc;
    }

    /** Number of day (night = false) or night (night = true) styles. */
    public int getCount(boolean night) {
        return night ? nightCount : dayCount;
    }

    /**
     * Returns the n-th day or night style (0 <= n < {@link #getCount}), counting the day (or night) theme
     * ranges in directory order, so a uniform n gives every entry of that kind the same chance.
     */
    public Entry get(boolean night, int n) {
        if (n < 0) {
            return null;
        }
        for (int t = 0; t < themeCount; t++) {
            if (themeNight[t] != night) {
                continue;
            }
            if (n < themeRecords[t]) {
                int record = themeFirst[t] + n;
                Entry e = new Entry(themeKeys[t], night, data, HEADER_SIZE + DIR_ENTRY_SIZE * themeCount + RECORD_SIZE * record);
                return e.isValid() ? e : null;
            }
            n -= themeRecords[t];
        }
        return null;
    }

    /**
     * Loads and fully verifies the bundled table (magic, version, sizes, directory, CRC-32). The parsed table is
     * immutable and cached, so later calls are cheap and any thread may call this.
     */
    public static StyleTable load(Context context) throws IOException {
        SoftReference<StyleTable> ref = cache;
        StyleTable cached = ref != null ? ref.get() : null;
        if (cached != null) {
            return cached;
        }
        byte[] bytes;
        try (InputStream in = context.getAssets().open(ASSET_NAME)) { // compressed in the APK: open(), not openFd()
            ByteArrayOutputStream out = new ByteArrayOutputStream(1 << 20);
            byte[] buf = new byte[1 << 16];
            int r;
            while ((r = in.read(buf)) != -1) {
                out.write(buf, 0, r);
            }
            bytes = out.toByteArray();
        }
        StyleTable table = parse(bytes);
        cache = new SoftReference<>(table);
        return table;
    }

    static StyleTable parse(byte[] bytes) throws IOException {
        ByteBuffer b = ByteBuffer.wrap(bytes); // big-endian
        if (bytes.length < HEADER_SIZE || b.getInt(0) != MAGIC) {
            throw new IOException("style table: bad magic");
        }
        int version = b.getShort(4) & 0xffff;
        int headerSize = b.getShort(6) & 0xffff;
        int themes = b.getShort(8) & 0xffff;
        int dirEntrySize = b.getShort(10) & 0xffff;
        int recordSize = b.getShort(12) & 0xffff;
        long records = b.getInt(16) & 0xffffffffL;
        int crc = b.getInt(20);
        if (version != VERSION || headerSize != HEADER_SIZE || dirEntrySize != DIR_ENTRY_SIZE || recordSize != RECORD_SIZE || themes == 0 || records == 0) {
            throw new IOException("style table: unsupported header");
        }
        if (bytes.length != HEADER_SIZE + (long) DIR_ENTRY_SIZE * themes + RECORD_SIZE * records) {
            throw new IOException("style table: bad size");
        }
        CRC32 crc32 = new CRC32();
        crc32.update(bytes, HEADER_SIZE, bytes.length - HEADER_SIZE);
        if ((int) crc32.getValue() != crc) {
            throw new IOException("style table: bad checksum");
        }
        String[] keys = new String[themes];
        boolean[] night = new boolean[themes];
        int[] first = new int[themes];
        int[] count = new int[themes];
        long expectedFirst = 0;
        for (int t = 0; t < themes; t++) {
            int off = HEADER_SIZE + DIR_ENTRY_SIZE * t;
            int len = 0;
            while (len < THEME_KEY_BYTES && bytes[off + len] != 0) {
                len++;
            }
            if (len == 0 || len == THEME_KEY_BYTES) {
                throw new IOException("style table: bad theme key");
            }
            keys[t] = new String(bytes, off, len, StandardCharsets.UTF_8);
            night[t] = (bytes[off + 20] & DIR_FLAG_NIGHT) != 0;
            long f = b.getInt(off + 24) & 0xffffffffL;
            long c = b.getInt(off + 28) & 0xffffffffL;
            if (f != expectedFirst || c == 0) {
                throw new IOException("style table: bad directory");
            }
            first[t] = (int) f;
            count[t] = (int) c;
            expectedFirst += c;
        }
        if (expectedFirst != records) {
            throw new IOException("style table: directory does not cover the records");
        }
        StyleTable table = new StyleTable(b, crc, keys, night, first, count);
        if (table.dayCount == 0 || table.nightCount == 0) {
            throw new IOException("style table: needs day and night styles");
        }
        return table;
    }
}
