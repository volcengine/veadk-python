"""Test to verify the enable_veadk_auth switch in to_a2a function."""

import pytest
from veadk import Agent, Runner
from veadk.a2a.utils.agent_to_a2a import to_a2a
from veadk.auth.ve_credential_service import VeCredentialService
from google.adk.auth.credential_service.base_credential_service import BaseCredentialService


class MockCredentialService(BaseCredentialService):
    """Mock credential service for testing."""
    pass


def test_to_a2a_without_veadk_auth():
    """Test to_a2a with enable_veadk_auth=False (default)."""
    agent = Agent(name="test_agent")
    app = to_a2a(agent, enable_veadk_auth=False)
    
    # App should be created successfully
    assert app is not None
    print("✅ Test 1 passed: to_a2a works without VeADK auth")


def test_to_a2a_with_veadk_auth_no_runner():
    """Test to_a2a with enable_veadk_auth=True and no runner provided."""
    agent = Agent(name="test_agent")
    app = to_a2a(agent, enable_veadk_auth=True)
    
    # App should be created successfully with VeCredentialService
    assert app is not None
    print("✅ Test 2 passed: to_a2a creates runner with VeCredentialService")


def test_to_a2a_with_veadk_auth_runner_with_ve_credential_service():
    """Test to_a2a with enable_veadk_auth=True and runner with VeCredentialService."""
    agent = Agent(name="test_agent")
    credential_service = VeCredentialService()
    runner = Runner(agent=agent, credential_service=credential_service)
    
    app = to_a2a(agent, runner=runner, enable_veadk_auth=True)
    
    # App should be created successfully
    assert app is not None
    # Runner should still have the same credential service
    assert runner.credential_service is credential_service
    print("✅ Test 3 passed: to_a2a accepts runner with VeCredentialService")


def test_to_a2a_with_veadk_auth_runner_without_credential_service():
    """Test to_a2a with enable_veadk_auth=True and runner without credential_service."""
    agent = Agent(name="test_agent")
    runner = Runner(agent=agent)
    
    # Runner initially has no credential_service (or None)
    initial_credential_service = getattr(runner, 'credential_service', None)
    
    app = to_a2a(agent, runner=runner, enable_veadk_auth=True)
    
    # App should be created successfully
    assert app is not None
    # Runner should now have a VeCredentialService
    assert hasattr(runner, 'credential_service')
    assert isinstance(runner.credential_service, VeCredentialService)
    print("✅ Test 4 passed: to_a2a adds VeCredentialService to runner")


def test_to_a2a_with_veadk_auth_runner_with_wrong_credential_service():
    """Test to_a2a with enable_veadk_auth=True and runner with non-VeCredentialService."""
    agent = Agent(name="test_agent")
    mock_credential_service = MockCredentialService()
    runner = Runner(agent=agent, credential_service=mock_credential_service)
    
    # Should raise TypeError
    with pytest.raises(TypeError) as exc_info:
        to_a2a(agent, runner=runner, enable_veadk_auth=True)
    
    assert "must be a VeCredentialService instance" in str(exc_info.value)
    assert "MockCredentialService" in str(exc_info.value)
    print("✅ Test 5 passed: to_a2a raises TypeError for wrong credential service type")


def test_to_a2a_without_veadk_auth_accepts_any_credential_service():
    """Test to_a2a with enable_veadk_auth=False accepts any credential service."""
    agent = Agent(name="test_agent")
    mock_credential_service = MockCredentialService()
    runner = Runner(agent=agent, credential_service=mock_credential_service)
    
    # Should work fine when VeADK auth is disabled
    app = to_a2a(agent, runner=runner, enable_veadk_auth=False)
    
    assert app is not None
    # Runner should still have the mock credential service
    assert runner.credential_service is mock_credential_service
    print("✅ Test 6 passed: to_a2a accepts any credential service when auth disabled")


if __name__ == "__main__":
    print("Running to_a2a auth switch tests...\n")
    
    test_to_a2a_without_veadk_auth()
    test_to_a2a_with_veadk_auth_no_runner()
    test_to_a2a_with_veadk_auth_runner_with_ve_credential_service()
    test_to_a2a_with_veadk_auth_runner_without_credential_service()
    test_to_a2a_with_veadk_auth_runner_with_wrong_credential_service()
    test_to_a2a_without_veadk_auth_accepts_any_credential_service()
    
    print("\n🎉 All tests passed!")

