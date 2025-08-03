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


def get_city_weather(city: str) -> dict[str, str]:
    """Retrieves the weather information of a given city. the args must in English"""
    fixed_weather = {
        "beijing": {"condition": "Sunny", "temperature": 25},
        "shanghai": {"condition": "Cloudy", "temperature": 22},
        "guangzhou": {"condition": "Rainy", "temperature": 28},
        "shenzhen": {"condition": "Partly cloudy", "temperature": 29},
        "chengdu": {"condition": "Windy", "temperature": 20},
        "hangzhou": {"condition": "Snowy", "temperature": -2},
        "wuhan": {"condition": "Humid", "temperature": 26},
        "chongqing": {"condition": "Hazy", "temperature": 30},
        "xi'an": {"condition": "Cool", "temperature": 18},
        "nanjing": {"condition": "Hot", "temperature": 32},
    }

    city = city.lower().strip()
    if city in fixed_weather:
        info = fixed_weather[city]
        return {"result": f"{info['condition']}, {info['temperature']}°C"}
    else:
        return {"result": f"Weather information not found for {city}"}


def get_location_weather(city: str) -> dict[str, str]:
    """Retrieves the weather information of a given city. the args must in English"""
    import random

    condition = random.choice(
        [
            "Sunny",
            "Cloudy",
            "Rainy",
            "Partly cloudy",
            "Windy",
            "Snowy",
            "Humid",
            "Hazy",
            "Cool",
            "Hot",
        ]
    )
    temperature = random.randint(-10, 40)
    return {"result": f"{condition}, {temperature}°C"}
