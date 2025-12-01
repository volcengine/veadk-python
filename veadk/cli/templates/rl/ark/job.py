# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from ark_sdk.resources.model_customization_job import ModelCustomizationJob
from ark_sdk.resources.pipeline_plugin import GRPOPipeline, PipelinePluginWrapper
from ark_sdk.types.model_customization_job import (
    ModelReference,
    FoundationModelReference,
    TrainingDataset,
    Data,
)

from plugins.random_reward import random_reward_fn
from plugins.raw_async_veadk_rollout import demo_veadk_rollout

if __name__ == "__main__":
    mcj = ModelCustomizationJob(
        name="sdk-job",
        model_reference=ModelReference(
            foundation_model=FoundationModelReference(
                name="doubao-seed-1-6-flash", model_version="250615"
            )
        ),
        hyperparameters={
            "batch_size": "32",
            "clip_ratio_high": "0.2",
            "clip_ratio_low": "0.2",
            "kl_coefficient": "0.001",
            "loss_agg_mode": "seq-mean-token-mean",
            "lr": "0.000001",
            "lr_warmup_steps": "5",
            "max_new_tokens": "1024",
            "num_generations": "8",
            "num_iterations_per_batch": "2",
            "save_every_n_steps": "10",
            "temperature": "1.0",
            "test_every_n_steps": "5",
            "test_num_generations": "1",
            "test_top_p": "1",
            "top_p": "1",
            "num_steps": "10",
        },
        data=Data(
            training_set=TrainingDataset(
                local_files=[
                    "./data/mcj_rollout_test_dataset.jsonl",
                ]
            )
        ),
        custom_rl_pipeline=GRPOPipeline(
            graders=[
                PipelinePluginWrapper(
                    plugin=random_reward_fn, envs={"foo": "bar"}, weight=0.5
                ),
            ],
            rollout=PipelinePluginWrapper(
                plugin=demo_veadk_rollout, envs={"foo": "bar"}
            ),
        ),
    )

    mcj.submit()
    print(f"Job submitted. view job at {mcj.url}")
