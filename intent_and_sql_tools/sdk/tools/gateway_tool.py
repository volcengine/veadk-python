from sdk.tools.runtime import get_brain, init_engine


def identify_intent(query: str) -> dict:
    brain = get_brain()
    return brain.generate_envelope(query)
