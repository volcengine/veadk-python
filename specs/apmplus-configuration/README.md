# APMPlus configuration

AppKey precedence: nonblank OBSERVABILITY_OPENTELEMETRY_APMPLUS_API_KEY, then TENANT_APMPLUS_APPKEY, then get_apmplus_token using existing environment/IAM credentials. Lookup is lazy and successful values are cached on each APMPlusConfig instance. Failure is not cached and never returned as an empty key. Malformed responses raise a sanitized ValueError. Explicit endpoint overrides the existing provider-aware default; no local collector is required for that remote default.
