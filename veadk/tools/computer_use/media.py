"""Adapt CUA tool-result images without changing provider model classes."""

from google.genai import types


def lift_screenshots(request):
    """Expose nested screenshot media to Ark without editing stored events."""
    expanded = []
    for content in request.contents:
        images, parts = [], []
        for part in content.parts or []:
            response = part.function_response
            if (
                response
                and response.name
                and response.name.startswith("cua_")
                and response.parts
            ):
                for media in response.parts:
                    blob = media.inline_data
                    if blob and blob.mime_type and blob.mime_type.startswith("image/"):
                        images.append(
                            types.Part.from_bytes(
                                data=blob.data, mime_type=blob.mime_type
                            )
                        )
                part = part.model_copy(
                    update={
                        "function_response": response.model_copy(update={"parts": None})
                    }
                )
            parts.append(part)
        expanded.append(content.model_copy(update={"parts": parts}))
        if images:
            expanded.append(types.Content(role="user", parts=images))
    request.contents = expanded
