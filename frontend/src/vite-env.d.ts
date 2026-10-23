/// <reference types="vite/client" />

// Optional development-only bridge to a Django instance with the storefront enabled.
interface ImportMetaEnv {
  readonly VITE_DJANGO_ORIGIN?: string;
  readonly VITE_STOREFRONT_ENABLED?: string;
}
