// A tiny, dependency-free STORE-only (no compression) ZIP builder.
//
// A store-only zip (compression method 0) is a fully valid archive that
// every unzip tool can open. We avoid DEFLATE entirely so there is nothing
// to depend on. The layout we emit is, in order:
//
//   [ Local File Header + file bytes ] * N      (one block per file)
//   [ Central Directory record ] * N
//   [ End Of Central Directory record ]
//
// All multi-byte integers are little-endian. Spec reference: PKWARE APPNOTE,
// sections 4.3.7 (local header), 4.3.12 (central directory), 4.3.16 (EOCD).

// --- CRC-32 (IEEE 802.3 polynomial 0xEDB88320) ------------------------------

// Precompute the 256-entry lookup table once at module load.
const CRC_TABLE: Uint32Array = (() => {
  const table = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) {
      c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    }
    table[n] = c >>> 0;
  }
  return table;
})();

function crc32(bytes: Uint8Array): number {
  let crc = 0xffffffff;
  for (let i = 0; i < bytes.length; i++) {
    crc = CRC_TABLE[(crc ^ bytes[i]) & 0xff] ^ (crc >>> 8);
  }
  return (crc ^ 0xffffffff) >>> 0;
}

// --- little-endian writers --------------------------------------------------

function writeU16(arr: number[], value: number): void {
  arr.push(value & 0xff, (value >>> 8) & 0xff);
}

function writeU32(arr: number[], value: number): void {
  arr.push(
    value & 0xff,
    (value >>> 8) & 0xff,
    (value >>> 16) & 0xff,
    (value >>> 24) & 0xff,
  );
}

// General purpose bit 11 (0x0800): file name / comment are UTF-8 encoded.
const UTF8_FLAG = 0x0800;
const VERSION_NEEDED = 20; // 2.0 — minimum for store/deflate.
const METHOD_STORE = 0; // compression method 0 = stored (no compression).

interface Prepared {
  nameBytes: Uint8Array;
  dataBytes: Uint8Array;
  crc: number;
  size: number;
  offset: number; // byte offset of this file's local header from start of archive.
}

export function buildZip(files: { path: string; content: string }[]): Blob {
  const encoder = new TextEncoder();

  // ---- local file headers + raw file data ----
  const localChunks: Uint8Array[] = [];
  const prepared: Prepared[] = [];
  let offset = 0;

  for (const file of files) {
    const nameBytes = encoder.encode(file.path);
    const dataBytes = encoder.encode(file.content);
    const crc = crc32(dataBytes);
    const size = dataBytes.length;

    // Local File Header — signature 0x04034b50, fixed 30 bytes + name. (4.3.7)
    const header: number[] = [];
    writeU32(header, 0x04034b50); // local file header signature
    writeU16(header, VERSION_NEEDED); // version needed to extract
    writeU16(header, UTF8_FLAG); // general purpose bit flag (UTF-8)
    writeU16(header, METHOD_STORE); // compression method = store
    writeU16(header, 0); // last mod file time
    writeU16(header, 0); // last mod file date
    writeU32(header, crc); // crc-32
    writeU32(header, size); // compressed size (== uncompressed for store)
    writeU32(header, size); // uncompressed size
    writeU16(header, nameBytes.length); // file name length
    writeU16(header, 0); // extra field length

    const headerBytes = Uint8Array.from(header);
    localChunks.push(headerBytes, nameBytes, dataBytes);

    prepared.push({ nameBytes, dataBytes, crc, size, offset });
    offset += headerBytes.length + nameBytes.length + dataBytes.length;
  }

  const centralDirOffset = offset;

  // ---- central directory ----
  const centralChunks: Uint8Array[] = [];
  let centralSize = 0;

  for (const p of prepared) {
    // Central Directory File Header — signature 0x02014b50, fixed 46 bytes
    // + name. (4.3.12)
    const rec: number[] = [];
    writeU32(rec, 0x02014b50); // central file header signature
    writeU16(rec, VERSION_NEEDED); // version made by
    writeU16(rec, VERSION_NEEDED); // version needed to extract
    writeU16(rec, UTF8_FLAG); // general purpose bit flag (UTF-8)
    writeU16(rec, METHOD_STORE); // compression method = store
    writeU16(rec, 0); // last mod file time
    writeU16(rec, 0); // last mod file date
    writeU32(rec, p.crc); // crc-32
    writeU32(rec, p.size); // compressed size
    writeU32(rec, p.size); // uncompressed size
    writeU16(rec, p.nameBytes.length); // file name length
    writeU16(rec, 0); // extra field length
    writeU16(rec, 0); // file comment length
    writeU16(rec, 0); // disk number start
    writeU16(rec, 0); // internal file attributes
    writeU32(rec, 0); // external file attributes
    writeU32(rec, p.offset); // relative offset of local header

    const recBytes = Uint8Array.from(rec);
    centralChunks.push(recBytes, p.nameBytes);
    centralSize += recBytes.length + p.nameBytes.length;
  }

  // ---- end of central directory ----
  // EOCD — signature 0x06054b50, fixed 22 bytes (no zip comment). (4.3.16)
  const eocd: number[] = [];
  writeU32(eocd, 0x06054b50); // end of central dir signature
  writeU16(eocd, 0); // number of this disk
  writeU16(eocd, 0); // disk with start of central directory
  writeU16(eocd, prepared.length); // central dir records on this disk
  writeU16(eocd, prepared.length); // total central dir records
  writeU32(eocd, centralSize); // size of central directory
  writeU32(eocd, centralDirOffset); // offset of central directory
  writeU16(eocd, 0); // zip file comment length

  // ---- concatenate everything into one Uint8Array ----
  const allChunks: Uint8Array[] = [
    ...localChunks,
    ...centralChunks,
    Uint8Array.from(eocd),
  ];
  const total = allChunks.reduce((sum, c) => sum + c.length, 0);
  const out = new Uint8Array(total);
  let pos = 0;
  for (const chunk of allChunks) {
    out.set(chunk, pos);
    pos += chunk.length;
  }

  return new Blob([out], { type: "application/zip" });
}
