// Preparing files for a chat message in the browser: images are shrunk (the API takes at most 5 MB and 1568 px is plenty to read a
// screenshot), everything is turned into base64. The daemon checks again (rdt/attachments.py) and never trusts names or MIME types.
export const MAX_FILES = 6;
const MAX_IMAGE_BYTES = 5 * 1024 * 1024;
const MAX_PDF = 10 * 1024 * 1024;
const MAX_TEXT_READ = 1024 * 1024;
const MAX_SIDE = 1568;
const TEXT_EXT = ['txt', 'log', 'csv', 'tsv', 'json', 'jsonl', 'md', 'yaml', 'yml', 'xml', 'ini', 'toml', 'c', 'h', 'cpp', 'hpp', 'py', 'js', 'ts', 'ps1', 'bat', 'sh', 'map', 'ld', 's', 'svd', 'html', 'css', 'cfg', 'conf', 'ioc'];

const toBase64 = (buf) => {
  let s = '';
  const b = new Uint8Array(buf);
  for (let i = 0; i < b.length; i += 0x8000) s += String.fromCharCode.apply(null, b.subarray(i, i + 0x8000));
  return btoa(s);
};

async function shrink(file) {
  // Re-encode a big image: scaled so the longest side is MAX_SIDE, as JPEG (PNG stays PNG when it has no photo content to save).
  const bmp = await createImageBitmap(file);
  const k = Math.min(1, MAX_SIDE / Math.max(bmp.width, bmp.height));
  if (k === 1 && file.size <= 3 * 1024 * 1024) { bmp.close?.(); return file; }
  const c = document.createElement('canvas');
  c.width = Math.round(bmp.width * k); c.height = Math.round(bmp.height * k);
  const g = c.getContext('2d');
  g.fillStyle = '#fff'; g.fillRect(0, 0, c.width, c.height); // JPEG has no transparency
  g.drawImage(bmp, 0, 0, c.width, c.height);
  bmp.close?.();
  const blob = await new Promise((r) => c.toBlob(r, 'image/jpeg', 0.9));
  return new File([blob], file.name.replace(/\.[^.]+$/, '') + '.jpg', { type: 'image/jpeg' });
}

// Returns { item: { name, kind, size, data, preview }, error: 'key' }; the caller shows the error key through i18n.
export async function prepareFile(file) {
  const ext = (file.name.split('.').pop() || '').toLowerCase();
  const isImage = file.type.startsWith('image/') || ['png', 'jpg', 'jpeg', 'gif', 'webp'].includes(ext);
  try {
    if (isImage) {
      let f = file;
      if (file.type !== 'image/gif') f = await shrink(file);   // a GIF is sent as it is (re-encoding would drop the animation)
      if (f.size > MAX_IMAGE_BYTES) return { error: 'chat.tooBig', name: file.name };
      return { item: { name: f.name || 'image.png', kind: 'image', size: f.size, data: toBase64(await f.arrayBuffer()), preview: URL.createObjectURL(f) } };
    }
    if (ext === 'pdf' || file.type === 'application/pdf') {
      if (file.size > MAX_PDF) return { error: 'chat.tooBig', name: file.name };
      return { item: { name: file.name, kind: 'pdf', size: file.size, data: toBase64(await file.arrayBuffer()), preview: null } };
    }
    if (TEXT_EXT.includes(ext)) {
      if (file.size > MAX_TEXT_READ) return { error: 'chat.tooBig', name: file.name };
      return { item: { name: file.name, kind: 'text', size: file.size, data: toBase64(await file.arrayBuffer()), preview: null } };
    }
  } catch {
    return { error: 'chat.unreadable', name: file.name };
  }
  return { error: 'chat.unsupported', name: file.name };
}
