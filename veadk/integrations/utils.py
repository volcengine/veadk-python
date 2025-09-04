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

from typing import Callable, Type


def vesource(source_name: str, source_func: Callable):
    """Automated resource management for Volcengine.

    Args:
        source_name (str): The name of the source.
        source_func (Callable): The function to call for the source.

    Returns:
        str: The result of the source function.
    """

    def decorator(cls: Type):
        # record cache source_name -> _source_name
        private_source_name = f"_{source_name}"
        setattr(cls, private_source_name, "")

        def getattribute(self, name: str):
            if name != source_name:
                return object.__getattribute__(self, name)
            if name == source_name:
                source = object.__getattribute__(self, name)

                if source:
                    return source
                elif not source and not getattr(cls, private_source_name):
                    source = source_func()
                    setattr(cls, private_source_name, source)
                    return source
                elif not source and getattr(cls, private_source_name):
                    return getattr(cls, private_source_name)
            return source

        setattr(cls, "__getattribute__", getattribute)
        return cls

    return decorator
