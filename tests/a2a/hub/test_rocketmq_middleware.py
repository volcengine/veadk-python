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

"""Unit tests for the RocketMQ A2A middleware.

All RocketMQ I/O (Producer/PushConsumer/Message) is mocked; no broker contact.
"""

from unittest.mock import Mock, patch

import pytest

from rocketmq.client import ConsumeStatus, ReceivedMessage

from veadk.a2a.hub.rocketmq_middleware import RocketMQAgentClient, RocketMQClient

MODULE = "veadk.a2a.hub.rocketmq_middleware"


@pytest.fixture
def mock_producer():
    """Patch the Producer class and yield the instance the client will hold."""
    with patch(f"{MODULE}.Producer") as producer_cls:
        instance = Mock()
        producer_cls.return_value = instance
        yield producer_cls, instance


def _make_client():
    return RocketMQClient(
        name="client1",
        producer_group="pg",
        name_server_addr="ns:9876",
        access_key="ak",
        access_secret="sk",
    )


def test_client_init_configures_and_starts_producer(mock_producer):
    producer_cls, producer = mock_producer
    client = _make_client()

    # Attributes stored verbatim.
    assert client.name == "client1"
    assert client.producer_group == "pg"
    assert client.name_server_addr == "ns:9876"
    assert client.access_key == "ak"
    assert client.access_secret == "sk"

    producer_cls.assert_called_once_with("pg")
    producer.set_name_server_address.assert_called_once_with("ns:9876")
    producer.set_session_credentials.assert_called_once_with("ak", "sk", "")
    producer.start.assert_called_once_with()


def test_send_msg_builds_message_and_sends_oneway(mock_producer):
    _, producer = mock_producer
    with patch(f"{MODULE}.Message") as message_cls:
        msg = Mock()
        message_cls.return_value = msg
        client = _make_client()
        client.send_msg("topicA", "hello", key="k1", tag="t1")

    message_cls.assert_called_once_with("topicA")
    msg.set_keys.assert_called_once_with("k1")
    msg.set_tags.assert_called_once_with("t1")
    msg.set_body.assert_called_once_with("hello")
    producer.send_oneway.assert_called_once_with(msg)


def test_send_msg_default_key_and_tag(mock_producer):
    _, _producer = mock_producer
    with patch(f"{MODULE}.Message") as message_cls:
        msg = Mock()
        message_cls.return_value = msg
        client = _make_client()
        client.send_msg("topicA", "body")

    msg.set_keys.assert_called_once_with("")
    msg.set_tags.assert_called_once_with("")


def test_start_consumer_subscribes_and_starts(mock_producer):
    _, _producer = mock_producer
    callback = Mock()
    with (
        patch(f"{MODULE}.PushConsumer") as consumer_cls,
        patch(f"{MODULE}.time.sleep", side_effect=KeyboardInterrupt),
    ):
        consumer = Mock()
        consumer_cls.return_value = consumer
        client = _make_client()
        # The method loops forever on time.sleep; KeyboardInterrupt breaks out
        # after the setup we want to assert on has run.
        with pytest.raises(KeyboardInterrupt):
            client.start_consumer(topic="topicA", group="grp", callback=callback)

    consumer_cls.assert_called_once_with("grp")
    consumer.set_name_server_address.assert_called_once_with("ns:9876")
    consumer.set_session_credentials.assert_called_once_with("ak", "sk", "")
    consumer.subscribe.assert_called_once_with("topicA", callback, "")
    consumer.start.assert_called_once_with()


class _ConcreteAgentClient(RocketMQAgentClient):
    """Minimal concrete subclass to test the abstract base's shared logic."""

    def recv_msg_callback(self, msg: ReceivedMessage) -> ConsumeStatus:
        return ConsumeStatus.CONSUME_SUCCESS


def test_agent_client_is_abstract():
    # The base declares an abstractmethod, so it cannot be instantiated.
    with pytest.raises(TypeError):
        RocketMQAgentClient(  # type: ignore[abstract]
            agent=Mock(),
            rocketmq_client=Mock(),
            subscribe_topic="t",
            group="g",
        )


def test_agent_client_stores_attributes():
    agent = Mock()
    rmq = Mock()
    ac = _ConcreteAgentClient(
        agent=agent,
        rocketmq_client=rmq,
        subscribe_topic="topicA",
        group="grp",
    )
    assert ac.agent is agent
    assert ac.rocketmq_client is rmq
    assert ac.subscribe_topic == "topicA"
    assert ac.group == "grp"


def test_agent_client_listen_delegates_to_consumer():
    agent = Mock()
    agent.name = "agent1"
    rmq = Mock()
    ac = _ConcreteAgentClient(
        agent=agent,
        rocketmq_client=rmq,
        subscribe_topic="topicA",
        group="grp",
    )
    ac.listen()
    rmq.start_consumer.assert_called_once_with(
        topic="topicA",
        group="grp",
        callback=ac.recv_msg_callback,
    )
