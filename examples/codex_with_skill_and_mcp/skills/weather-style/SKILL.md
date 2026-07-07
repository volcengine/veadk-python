---
name: weather-style
description: How to answer weather questions. Use whenever the user asks about the weather in a city.
---

When the user asks about the weather in a city:

1. Call the `get_weather` tool with that city to get the current conditions.
2. Reply in exactly this format, on one line:

   `<city>: <condition>, <temperature>. Have a nice day!`

Do not invent conditions — always take them from the tool result.
