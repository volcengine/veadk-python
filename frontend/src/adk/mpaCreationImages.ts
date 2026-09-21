export function validCreationImage(value: string = ""): boolean {
  const image = value.trim();
  return (
    !image ||
    (image.length <= 1024 &&
      /^[A-Za-z0-9._:/@-]+$/.test(image) &&
      !image.includes("//") &&
      (!image.includes("@") || /^[^@]+@sha256:[a-fA-F0-9]{64}$/.test(image)))
  );
}
