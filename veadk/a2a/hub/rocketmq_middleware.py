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

import time
from abc import ABC, abstractmethod
from typing import Callable

from rocketmq.client import (
    ConsumeStatus,
    Message,
    Producer,
    PushConsumer,
    ReceivedMessage,
)

from veadk import Agent
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


class RocketMQClient:
    def __init__(
        self,
        name: str,
        producer_group: str,
        name_server_addr: str,
        access_key: str,
        access_secret: str,
    ):
        self.name = name

        self.producer_group = producer_group
        self.name_server_addr = name_server_addr
        self.access_key = access_key
        self.access_secret = access_secret

        self.producer = Producer(producer_group)
        self.producer.set_name_server_address(name_server_addr)
        self.producer.set_session_credentials(access_key, access_secret, "")
        self.producer.start()

    def send_msg(self, topic: str, msg_body: str, key: str = "", tag: str = ""):
        msg = Message(topic)
        msg.set_keys(key)
        msg.set_tags(tag)
        msg.set_body(msg_body)

        logger.info(
            f"Middleware client {self.name} send one-way message to topic {topic}: {msg_body}"
        )
        self.producer.send_oneway(msg)

        # self.producer.shutdown()

    def start_consumer(self, topic: str, group: str, callback: Callable):
        consumer = PushConsumer(group)
        consumer.set_name_server_address(self.name_server_addr)
        consumer.set_session_credentials(self.access_key, self.access_secret, "")

        # for trial, subscribe all tags
        consumer.subscribe(topic, callback, "")

        consumer.start()

        while True:
            time.sleep(3600)


class RocketMQAgentClient(ABC):
    def __init__(
        self,
        agent: Agent,
        rocketmq_client: RocketMQClient,
        subscribe_topic: str,
        group: str,
    ):
        self.agent = agent
        self.rocketmq_client = rocketmq_client

        self.subscribe_topic = subscribe_topic
        self.group = group

    def listen(self):
        logger.info(
            f"RocketMQ agent client {self.agent.name} start listening on topic {self.subscribe_topic}"
        )
        self.rocketmq_client.start_consumer(
            topic=self.subscribe_topic,
            group=self.group,
            callback=self.recv_msg_callback,
        )

    @abstractmethod
    def recv_msg_callback(self, msg: ReceivedMessage) -> ConsumeStatus: ...
