/// <reference types="vite/client" />

declare const __APP_VERSION__: string;

interface ImportMetaEnv {
  readonly VITE_GATEWAY_URL: string;
  readonly VITE_GATEWAY_TOKEN: string;
  readonly VITE_LEADER_URL: string;
  readonly VITE_PAPERCLIP_URL: string;
  readonly VITE_DRVP_COMPANY_ID: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
