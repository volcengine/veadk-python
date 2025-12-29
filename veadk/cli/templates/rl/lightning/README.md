# Agent Lightning

Agent Lightning 提供了灵活且可扩展的框架，实现了智能体（client）和训练（server）的完全解耦。
VeADK 与 Agent Lightning 集成，用户使用 VeADK 提供的脚手架，可以开发 VeADK Agent，然后运行 client 与 server 进行强化学习优化。

## 准备工作

在你的终端中运行以下命令，初始化一个 Agent Lightning 项目：

```bash
veadk rl init --platform lightning --workspace veadk_rl_lightning_project
```

该命令会在当前目录下创建一个名为 `veadk_rl_lightning_project` 的文件夹，其中包含了一个基本的基于 VeADK 和 Agent Lightning 的强化学习项目结构。
然后在终端1中运行以下命令，启动 client：

```bash
cd veadk_rl_lightning_project
python veadk_agent.py
```

然后在终端2中运行以下命令

- 首先重启 ray 集群：

```bash
cd veadk_rl_lightning_project
bash restart_ray.sh
```  

- 启动 server：

```bash
cd veadk_rl_lightning_project
bash train.sh
```

## 原理说明

生成后的项目结构如下，其中核心文件包括：

- agent_client: `*_agent.py` 中定义了agent的rollout逻辑和reward规则
- training_server: `train.sh` 定义了训练相关参数,用于启动训练服务器

```shell
veadk_rl_lightning_project
├── data 
    ├── demo_train.parquet # 训练数据,必须为 parquet 格式
    ├── demo_test.parquet # 测试数据,必须为 parquet 格式
└── demo_calculate_agent.py # agent的rollout逻辑和reward设定
└── train.sh # 训练服务器启动脚本,设定训练相关参数 
└── restart_ray.sh # 重启 ray 集群脚本
```

## 最佳实践案例

1. 脚手架中，基于 VeADK 的算术 Agent 进行强化学习优化
2. 启动 client (python demo_calculate_agent.py), 重启ray集群(bash restart_ray.sh), 最后启动训练服务器server (bash train.sh)，分别在终端1与终端2中运行以上命令
