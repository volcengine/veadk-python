# 基于方舟平台强化学习
方舟 RL 将强化学习过程进行了一定程度的封装，降低了复杂度。用户主要关注 rollout 中的 agent 逻辑、奖励函数的构建、训练样本的选择即可。
VeADK 与方舟平台 Agent RL 集成，用户使用 VeADK 提供的脚手架，可以开发 VeADK Agent，然后提交任务到方舟平台进行强化学习优化。
## 准备工作
在你的终端中运行以下命令，初始化一个强化学习项目：
```shell
veadk rl ark init workspace veadk_ark_rl_project
```
该命令会在当前目录下创建一个名为 `veadk_ark_rl_project` 的文件夹，其中包含了一个基本的强化学习项目结构。
然后在终端中运行以下命令，提交任务到方舟平台：
```shell
cd veadk_ark_rl_project
veadk rl ark submit
```
## 原理说明
生成后的项目结构如下，其中核心文件包括：
- 数据集: `data/*.jsonl`
- `/plugins`文件夹下的rollout和reward:
  - rollout ：用以规定agent的工作流，`raw_async_veadk_rollout.py`提供了使用在方舟rl中使用veadk agent的示例，
  - reward：给出强化学习所需的奖励值，在`random_reward.py`给出了示例
- `job.py`或`job.yaml`：用以配置训练参数，并指定需要使用的rollout和reward
```shell
veadk_ark_rl_project
├── data
    ├── *.jsonl # 训练数据
└── plugins
    ├── async_weather_rollout.py # 
    ├── config.yaml.example # VeADK agent 配置信息示例
    ├── random_reward.py # reward规则设定
    ├── raw_async_veadk_rollout.py # rollout工作流设定
    ├── raw_rollout.py # 
    └── test_utils.py #
    └── weather_rollout.py # 
├── job.py # 任务提交代码
├── job.yaml # 任务配置
├── test_agent.py # VeFaaS 测试脚本
```

## 运行
```bash
ark create mcj -f job.yaml
```
或
```bash
python job.py   
```