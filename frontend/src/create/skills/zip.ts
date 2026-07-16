// Minimal ZIP reader: walks the central directory, supports store (0) and
// deflate (8) via the browser's DecompressionStream("deflate-raw"). Extracted
// verbatim from the previous monolithic skills.ts so both the Skill Hub
// downloader and the local .zip uploader can share it.

export interface ZipEntry {
  name: string;
  text: string;
}

function u16(b: Uint8Array, o: number) {
  return b[o] | (b[o + 1] << 8);
}
function u32(b: Uint8Array, o: number) {
  return (b[o] | (b[o + 1] << 8) | (b[o + 2] << 16) | (b[o + 3] << 24)) >>> 0;
}

async function inflateRaw(data: Uint8Array): Promise<Uint8Array> {
  // DecompressionStream is available in modern browsers + Node 18+.
  const ds = new DecompressionStream("deflate-raw");
  // Copy into a fresh ArrayBuffer-backed view so the Blob typing is happy.
  const stream = new Blob([new Uint8Array(data)]).stream().pipeThrough(ds);
  const out = new Uint8Array(await new Response(stream).arrayBuffer());
  return out;
}

export async function unzip(buf: Uint8Array): Promise<ZipEntry[]> {
  // Find the End Of Central Directory record (signature 0x06054b50), scanning
  // backwards (it's within the last 65557 bytes).
  const EOCD = 0x06054b50;
  let eocd = -1;
  for (let i = buf.length - 22; i >= 0 && i > buf.length - 65557; i--) {
    if (u32(buf, i) === EOCD) {
      eocd = i;
      break;
    }
  }
  if (eocd < 0) throw new Error("无效的 zip：找不到 EOCD");

  const count = u16(buf, eocd + 10);
  let p = u32(buf, eocd + 16); // central directory offset
  const dec = new TextDecoder("utf-8");
  const entries: ZipEntry[] = [];

  for (let i = 0; i < count; i++) {
    if (u32(buf, p) !== 0x02014b50) break; // central dir header signature
    const method = u16(buf, p + 10);
    const compSize = u32(buf, p + 20);
    const nameLen = u16(buf, p + 28);
    const extraLen = u16(buf, p + 30);
    const commentLen = u16(buf, p + 32);
    const localOff = u32(buf, p + 42);
    const name = dec.decode(buf.subarray(p + 46, p + 46 + nameLen));

    // Local file header: 30 bytes fixed + name + extra, then file data.
    const lNameLen = u16(buf, localOff + 26);
    const lExtraLen = u16(buf, localOff + 28);
    const dataStart = localOff + 30 + lNameLen + lExtraLen;
    const raw = buf.subarray(dataStart, dataStart + compSize);

    let bytes: Uint8Array;
    if (method === 0) bytes = raw;
    else if (method === 8) bytes = await inflateRaw(raw);
    else {
      p += 46 + nameLen + extraLen + commentLen;
      continue; // unsupported method — skip
    }
    entries.push({ name, text: dec.decode(bytes) });
    p += 46 + nameLen + extraLen + commentLen;
  }
  return entries;
}
