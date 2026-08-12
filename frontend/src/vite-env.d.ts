/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_STUDIO_RELEASE_CHANGELOG?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
