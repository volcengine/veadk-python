export type CloudProvider = "volcengine" | "byteplus";
export type CloudRegion = "cn-beijing" | "cn-shanghai" | "ap-southeast-1";

export interface CloudRegionOption {
  value: CloudRegion;
  label: string;
}

export const BYTEPLUS_DEFAULT_REGION = "ap-southeast-1";
export const VOLCENGINE_DEFAULT_REGION = "cn-beijing";
export const BYTEPLUS_MODELARK_BASE_URL =
  "https://ark.ap-southeast.bytepluses.com/api/v3";
export const VOLCENGINE_MODELARK_BASE_URL =
  "https://ark.cn-beijing.volces.com/api/v3/";
export const BYTEPLUS_MODELARK_ACTIVATION_URL =
  "https://console.byteplus.com/ark/region:ark+ap-southeast-1/openManagement";
export const VOLCENGINE_MODELARK_ACTIVATION_URL =
  "https://console.volcengine.com/ark/region:ark+cn-beijing/openManagement";
export const BYTEPLUS_DEFAULT_MODEL_NAME = "dola-seed-2-1-turbo-260628";
export const VOLCENGINE_DEFAULT_MODEL_NAME = "doubao-seed-2-1-pro-260628";
export const BYTEPLUS_DEFAULT_EMBEDDING_NAME =
  "skylark-embedding-vision-250615";
export const VOLCENGINE_DEFAULT_EMBEDDING_NAME =
  "doubao-embedding-vision-250615";
export const BYTEPLUS_PLANNER_MODEL_NAME = "seed-2-0-lite-260228";
export const VOLCENGINE_PLANNER_MODEL_NAME = "doubao-seed-2-0-lite-260428";
export const BYTEPLUS_DEFAULT_IMAGE_MODEL_NAME = "dola-seedream-5-0-pro-260628";
export const VOLCENGINE_DEFAULT_IMAGE_MODEL_NAME = "doubao-seedream-5-0-260128";
export const BYTEPLUS_DEFAULT_IMAGE_EDIT_MODEL_NAME = "seededit-3-0-i2i-250628";
export const VOLCENGINE_DEFAULT_IMAGE_EDIT_MODEL_NAME =
  "doubao-seededit-3-0-i2i-250628";
export const BYTEPLUS_DEFAULT_VIDEO_MODEL_NAME = "dreamina-seedance-2-0-260128";
export const VOLCENGINE_DEFAULT_VIDEO_MODEL_NAME = "doubao-seedance-2-0-260128";

export function cloudRegionOptions(
  provider: CloudProvider,
): CloudRegionOption[] {
  return provider === "byteplus"
    ? [{ value: BYTEPLUS_DEFAULT_REGION, label: BYTEPLUS_DEFAULT_REGION }]
    : [
        { value: "cn-beijing", label: adkT("cloudRegion.cnBeijing") },
        { value: "cn-shanghai", label: adkT("cloudRegion.cnShanghai") },
      ];
}

export function defaultCloudRegion(provider: CloudProvider): CloudRegion {
  return cloudRegionOptions(provider)[0]?.value || VOLCENGINE_DEFAULT_REGION;
}

const SUPPORTED_CLOUD_REGIONS: ReadonlySet<string> = new Set([
  "cn-beijing",
  "cn-shanghai",
  "ap-southeast-1",
]);

export function isSupportedCloudRegion(value: unknown): value is CloudRegion {
  return typeof value === "string" && SUPPORTED_CLOUD_REGIONS.has(value);
}

export function formatCloudRegion(
  region: string,
  provider?: CloudProvider,
): string {
  const options = provider
    ? cloudRegionOptions(provider)
    : [...cloudRegionOptions("volcengine"), ...cloudRegionOptions("byteplus")];
  return (
    options.find((option) => option.value === region)?.label || region || "-"
  );
}

export function defaultModelName(provider: CloudProvider): string {
  return provider === "byteplus"
    ? BYTEPLUS_DEFAULT_MODEL_NAME
    : VOLCENGINE_DEFAULT_MODEL_NAME;
}

export function defaultModelApiBase(provider: CloudProvider): string {
  return provider === "byteplus"
    ? BYTEPLUS_MODELARK_BASE_URL
    : VOLCENGINE_MODELARK_BASE_URL;
}

export function modelActivationConsoleUrl(provider: CloudProvider): string {
  return provider === "byteplus"
    ? BYTEPLUS_MODELARK_ACTIVATION_URL
    : VOLCENGINE_MODELARK_ACTIVATION_URL;
}

export function defaultEmbeddingModelName(provider: CloudProvider): string {
  return provider === "byteplus"
    ? BYTEPLUS_DEFAULT_EMBEDDING_NAME
    : VOLCENGINE_DEFAULT_EMBEDDING_NAME;
}

export function plannerModelName(provider: CloudProvider): string {
  return provider === "byteplus"
    ? BYTEPLUS_PLANNER_MODEL_NAME
    : VOLCENGINE_PLANNER_MODEL_NAME;
}

export function defaultImageModelName(provider: CloudProvider): string {
  return provider === "byteplus"
    ? BYTEPLUS_DEFAULT_IMAGE_MODEL_NAME
    : VOLCENGINE_DEFAULT_IMAGE_MODEL_NAME;
}

export function defaultImageEditModelName(provider: CloudProvider): string {
  return provider === "byteplus"
    ? BYTEPLUS_DEFAULT_IMAGE_EDIT_MODEL_NAME
    : VOLCENGINE_DEFAULT_IMAGE_EDIT_MODEL_NAME;
}

export function defaultVideoModelName(provider: CloudProvider): string {
  return provider === "byteplus"
    ? BYTEPLUS_DEFAULT_VIDEO_MODEL_NAME
    : VOLCENGINE_DEFAULT_VIDEO_MODEL_NAME;
}
import { adkT } from "./i18n";
