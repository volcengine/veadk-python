# APMPlus 配置

AppKey 优先级：非空 OBSERVABILITY_OPENTELEMETRY_APMPLUS_API_KEY，其次 TENANT_APMPLUS_APPKEY，最后 get_apmplus_token 使用现有环境/IAM凭据。延迟获取，成功值缓存在每个 APMPlusConfig 实例。失败不缓存，也不返回空key。异常响应抛脱敏 ValueError。显式 endpoint 覆盖现有按云平台选择的默认值；远程默认地址不依赖本地collector。
