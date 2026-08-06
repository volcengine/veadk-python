export type CloudProvider = "volcengine" | "byteplus";

export interface CloudRegionOption {
  value: string;
  label: string;
}

export const BYTEPLUS_DEFAULT_REGION = "ap-southeast-1";
export const VOLCENGINE_DEFAULT_REGION = "cn-beijing";
export const BYTEPLUS_MODELARK_BASE_URL = "https://ark.ap-southeast.bytepluses.com/api/v3";
export const VOLCENGINE_MODELARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3/";
export const BYTEPLUS_DEFAULT_MODEL_NAME = "seed-2-0-lite-260228";
export const VOLCENGINE_DEFAULT_MODEL_NAME = "doubao-seed-2-1-pro-260628";
export const BYTEPLUS_DEFAULT_EMBEDDING_NAME = "skylark-embedding-vision-250615";
export const VOLCENGINE_DEFAULT_EMBEDDING_NAME = "doubao-embedding-vision-250615";
export const BYTEPLUS_PLANNER_MODEL_NAME = "seed-2-0-lite-260228";
export const VOLCENGINE_PLANNER_MODEL_NAME = "doubao-seed-2-0-lite-260428";

const VOLCENGINE_REGIONS: CloudRegionOption[] = [
  { value: "cn-beijing", label: "华北 2（北京）" },
  { value: "cn-shanghai", label: "华东 2（上海）" },
];

const BYTEPLUS_REGIONS: CloudRegionOption[] = [
  { value: BYTEPLUS_DEFAULT_REGION, label: "ap-southeast-1 (Singapore)" },
];

export function cloudRegionOptions(provider: CloudProvider): CloudRegionOption[] {
  return provider === "byteplus" ? BYTEPLUS_REGIONS : VOLCENGINE_REGIONS;
}

export function defaultCloudRegion(provider: CloudProvider): string {
  return cloudRegionOptions(provider)[0]?.value || VOLCENGINE_DEFAULT_REGION;
}

export function formatCloudRegion(region: string, provider?: CloudProvider): string {
  const options = provider
    ? cloudRegionOptions(provider)
    : [...VOLCENGINE_REGIONS, ...BYTEPLUS_REGIONS];
  return options.find((option) => option.value === region)?.label || region || "-";
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
