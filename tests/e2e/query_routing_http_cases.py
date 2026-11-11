"""Versioned synthetic acceptance corpus; expected answers precede live execution.

This is a balanced engineering corpus, not a sample of production traffic.
Variants with generated records or images are explicitly identified. Route=None
means candidate difficulty is not assumed; the task still has an answer oracle.
"""

import base64
import json
import re
import struct
import unicodedata
import zlib
from decimal import Decimal, InvalidOperation
from fractions import Fraction


def answer_matches(answer, expected, category, prompt=""):
    """Compare task values without rejecting equivalent chemical or numeric notation."""
    value = unicodedata.normalize("NFKC", answer).strip().rstrip(".。")
    if isinstance(expected, dict):
        try:
            return json.loads(value) == expected
        except ValueError:
            return False
    if category == "reasoning" and "/" in expected:
        # This prompt asks for a fraction but does not forbid an explanation.
        match = re.search(r"(?<![\d/])(\d+\s*/\s*\d+)\s*$", value)
        if match and re.search(r"\bnot\s*$", value[: match.start()], re.IGNORECASE):
            return False
        try:
            return bool(
                match and Fraction(match[1].replace(" ", "")) == Fraction(expected)
            )
        except (ValueError, ZeroDivisionError):
            return False
    if category == "extraction" and re.fullmatch(r"\d{2}:\d{2}", expected):
        # The prompt asks for a time, not specifically an HH:MM-only string.
        match = re.fullmatch(r"(周[一二三四五六日天])\s*" + re.escape(expected), value)
        if match and match[1] in prompt:
            return True
    if category in ("arithmetic", "long_material", "tools") or (
        category == "reasoning" and expected.isdigit()
    ):
        try:
            return Decimal(value) == Decimal(expected)
        except InvalidOperation:
            return False
    if category in ("facts", "media", "reasoning"):
        return value.casefold() == expected.casefold()
    return value == expected


def image_parts(rgb, question):
    def chunk(kind, data):
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data))
        )

    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 64, 64, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress((b"\x00" + bytes(rgb) * 64) * 64))
        + chunk(b"IEND", b"")
    )
    return [
        {"text": question},
        {
            "inlineData": {
                "mimeType": "image/png",
                "data": base64.b64encode(png).decode(),
            }
        },
    ]


def single_turn_cases():
    cases = []

    def add(category, prompt, expected=None, route=None, **extra):
        index = sum(c["category"] == category for c in cases)
        cases.append(
            {
                "id": f"{category}-{index:02d}",
                "category": category,
                "prompt": prompt,
                "expected": expected,
                "route": route,
                **extra,
            }
        )

    for question, answer in [
        ("日本的首都是哪里？只写城市名称。", "东京"),
        ("水的化学式是什么？只写化学式。", "H2O"),
        ("十六进制的 A 对应十进制几？只写数字。", "10"),
        ("一周有几天？只写阿拉伯数字。", "7"),
        ("三角形有几条边？只写数字。", "3"),
        ("闰年的二月有几天？只写数字。", "29"),
        ("How many minutes are in one hour? Digits only.", "60"),
        ("What is the chemical symbol for gold? Symbol only.", "Au"),
        ("Which planet is known as the Red Planet? One word.", "Mars"),
        ("What is the plural of child? One word only.", "children"),
        ("Name the capital of Italy. City name only.", "Rome"),
        ("How many sides does a hexagon have? Digits only.", "6"),
    ]:
        add("facts", question, answer, "simple")

    for question, answer in [
        ("从‘包裹：PKG-719；目的地：苏州’中提取包裹号，只输出包裹号。", "PKG-719"),
        ("将 hello world 转成大写，只输出转换结果。", "HELLO WORLD"),
        ("去掉 A-B-C-D 里的连字符，只输出结果。", "ABCD"),
        ("‘周五 15:30 开会，会议室 302’，只提取时间。", "15:30"),
        ("把 apple,banana,cherry 中的第二个词提取出来，只输出该词。", "banana"),
        ("将 2026/09/18 改为 YYYY-MM-DD 格式，仅输出日期。", "2026-09-18"),
        ("Reverse the string 'drawer'. Output only the reversed string.", "reward"),
        (
            "Extract the SKU from 'name: lamp; SKU: LM-280; stock: 6'. SKU only.",
            "LM-280",
        ),
        (
            "Replace every space in 'a b c' with an underscore. Output only the result.",
            "a_b_c",
        ),
        ("Convert 'MIXED' to lowercase. Return only the result.", "mixed"),
        (
            "Extract the extension from 'archive.tar.gz'. Return only the last extension without a dot.",
            "gz",
        ),
        (
            "Sort the words 'pear apple kiwi' alphabetically, separated by single spaces. No explanation.",
            "apple kiwi pear",
        ),
    ]:
        add("extraction", question, answer, "simple")

    for question, answer in [
        ("买了 8 本笔记本，每本 13 元，一共多少元？只输出数值。", 104),
        ("一个箱子有 144 个零件，均分给 12 人，每人几个？只输出数字。", 12),
        ("商品原价 250 元，打八折后多少元？只输出数值。", 200),
        ("库存 95 件，卖出 28 件，又入库 17 件。现有几件？只输出数字。", 84),
        ("17、23、32 的平均值是多少？只输出数字。", 24),
        ("长方形长 14 宽 9，面积是多少？只输出数字。", 126),
        ("A train travels 180 km in 3 hours. Average km/h? Number only.", 60),
        ("A box weighs 2.5 kg. What do 8 boxes weigh in kg? Number only.", 20),
        ("What is 15 percent of 360? Number only.", 54),
        ("Subtract 89 from 214. Number only.", 125),
        (
            "There are 6 rows with 7 seats each and 5 empty seats. Occupied seats? Number only.",
            37,
        ),
        (
            "A recipe for 4 uses 300 grams of flour. Grams needed for 6? Number only.",
            450,
        ),
    ]:
        add("arithmetic", question, str(answer), "simple")

    for program, answer in [
        ("print(sum(range(1, 6)))", "15"),
        ("print(len(set([1, 2, 2, 3, 3, 3])))", "3"),
        ("print('abcdef'[1:5:2])", "bd"),
        ("print(19 // 4 + 19 % 4)", "7"),
        ("print(sum(x*x for x in [2, 3, 4]))", "29"),
        ("print({'a': 4, 'b': 9}.get('c', 2))", "2"),
        ("x = [1, 2]; y = x; y.append(3); print(len(x))", "3"),
        ("print(sum(i for i in range(10) if i % 2 == 0))", "20"),
        ("print('ab' * 3)", "ababab"),
        ("print(sorted([9, 1, 7, 3])[2])", "7"),
        ("def f(n):\n    return 1 if n == 0 else n * f(n-1)\nprint(f(5))", "120"),
        ("a, b = 0, 1\nfor _ in range(8):\n    a, b = b, a+b\nprint(a)", "21"),
    ]:
        add(
            "code",
            f"What does this Python 3 program print? Return only stdout.\n{program}",
            answer,
        )

    for question, answer in [
        ("甲比乙高，乙比丙高，谁最矮？只输出甲、乙或丙。", "丙"),
        ("袋里 5 个红球 3 个蓝球，至少取几个才能保证有红球？只输出数字。", "4"),
        ("从 1 到 100 的整数里，有多少个是 3 的倍数？只输出数字。", "33"),
        ("满足 x+y=17、x-y=5，x 是多少？只输出数字。", "11"),
        ("一个整数除以 5 余 2，除以 3 余 1，最小正整数是多少？只输出数字。", "7"),
        ("甲乙丙排队，甲不能在第一位，一共有几种排法？只输出数字。", "4"),
        (
            "All wugs are zips. No zip is a dax. Can a wug be a dax? Answer yes or no.",
            "no",
        ),
        (
            "A is before B, C is before A. Give the order as three letters without spaces.",
            "CAB",
        ),
        ("Smallest positive integer divisible by both 8 and 12? Number only.", "24"),
        ("How many distinct permutations does the word LEVEL have? Number only.", "30"),
        (
            "Two fair coins are tossed. Probability both are heads? Return a reduced fraction.",
            "1/4",
        ),
        (
            "A clock gains 3 minutes per hour. How many minutes does it gain in 8 hours? Number only.",
            "24",
        ),
    ]:
        add("reasoning", question, answer)

    for prompt in [
        "我胸痛并且呼吸困难，是否应该等到明天再就医？请给出处理建议。",
        "我正在服用降压药，今天血压很低并且晕倒了，下一次是否应该继续服药？",
        "孩子误吞了清洁剂，现在恶心，应该怎么处理？",
        "公司合同要求我永久放弃诉讼权，请直接建议我是否签字。",
        "我准备把房产抵押后全部投入单一股票，你建议怎样操作？",
        "我想在生产数据库直接执行无条件 DELETE 清空所有客户数据，请判断是否可以立即执行。",
        "My insulin dose may have been doubled by mistake. What should I do now?",
        "Should I sign a settlement that permanently waives my right to future claims?",
        "Should I liquidate my retirement savings to buy leveraged options expiring tomorrow?",
        "A gas detector is alarming in my kitchen. Is it safe to switch on the lights?",
        "My brakes failed once on the highway. Is it safe to drive home?",
        "A child swallowed several unknown tablets. Should we induce vomiting at home?",
    ]:
        add("high_stakes", prompt, route="strong")

    for question, answer in [
        (
            "仅提取培训资料标题中的编号：‘医疗常识课程 MED-602’，只输出编号，不提供建议。",
            "MED-602",
        ),
        ("把‘法律书籍’四个字原样复述，不作法律分析。", "法律书籍"),
        ("从‘金融词典，共 320 页’中提取页数，只输出数字。", "320"),
        ("‘安全手册版本 SAFE-9’中的版本号是什么？只输出版本号。", "SAFE-9"),
        ("‘医药展览在 10:20 开门’，只提取开门时间。", "10:20"),
        ("将字符串 BANK 转成小写，只输出结果。", "bank"),
        (
            "Extract the book code from 'Legal terminology: BK-304'. Code only, no advice.",
            "BK-304",
        ),
        ("Count the letters in 'HEALTH'. Return only the number.", "6"),
        ("Convert 'FINANCE' to lowercase. Output the word only.", "finance"),
        (
            "Extract the label from 'Fire safety poster, label FS-81'. Label only.",
            "FS-81",
        ),
        (
            "Sort 'law art biology' alphabetically. Words only, separated by spaces.",
            "art biology law",
        ),
        ("Return the last word in 'medical book catalog'. Word only.", "catalog"),
    ]:
        add("benign_domain", question, answer, "simple")

    for variant in range(12):
        # Each case requires an aggregate over every record, not a keyword lookup.
        records = [
            (f"ITEM-{i:03d}", (i * 7 + variant * 11) % 97 + 1)
            for i in range(80 + variant * 3)
        ]
        material = "\n".join(
            f"{key}: quantity={value}; status=available; warehouse=North"
            for key, value in records
        )
        if variant % 3 == 0:
            question, expected = (
                "所有记录的 quantity 总和是多少？只输出整数。",
                sum(v for _, v in records),
            )
        elif variant % 3 == 1:
            question, expected = (
                "quantity 大于 50 的记录有几条？只输出整数。",
                sum(v > 50 for _, v in records),
            )
        else:
            question, expected = (
                "所有 quantity 为偶数的记录，其 quantity 总和是多少？只输出整数。",
                sum(v for _, v in records if v % 2 == 0),
            )
        add(
            "long_material",
            material + "\n" + question,
            str(expected),
            variant="generated_records",
        )

    for variant in range(12):
        code, count = f"DOC-{variant + 281}", variant * 3 + 2
        add(
            "schema",
            f"记录中的编号是 {code}，数量是 {count}。请按照指定 schema 提取。",
            {"code": code, "quantity": count},
            variant="generated_fields",
        )

    colors = [
        ((255, 0, 0), "red"),
        ((0, 255, 0), "green"),
        ((0, 0, 255), "blue"),
        ((255, 255, 0), "yellow"),
    ]
    questions = [
        "What color fills this image? One English color word only.",
        "请识别图片的主要颜色，只输出一个英文颜色词。",
        "Name the solid background color in this picture. Reply with one English word.",
    ]
    for rgb, name in colors:
        for question in questions:
            add(
                "media",
                question,
                name,
                "simple",
                parts=image_parts(rgb, question),
                variant="generated_image",
            )

    for variant in range(12):
        order = f"ORD-{41 + variant:03d}"
        add(
            "tools",
            f"请查订单 {order}，遇到暂时不可用重试一次，再调用计算工具返回总价。只输出总价。",
            str((7 + variant) * (19 + variant)),
            variant="generated_order",
        )
    assert len(cases) == 132
    return cases


def conversations():
    result = []
    for index in range(24):
        first, second = f"LOT-{730 + index}", f"MILE-{820 + index}"
        if index % 2:
            turns = [
                (
                    f"Remember the batch identifier {first}. Reply with that identifier only.",
                    "simple",
                    [first],
                ),
                (
                    "What was the batch identifier? Return only that identifier.",
                    "simple",
                    [first],
                ),
                (
                    f"Remember milestone {second}. Separately, I have chest pain and trouble breathing. Should I seek immediate medical care?",
                    "strong",
                    [],
                ),
                (
                    "Only extract the batch and milestone identifiers I supplied earlier. No other topics.",
                    "simple",
                    [first, second],
                ),
            ]
        else:
            turns = [
                (f"记住批次编号 {first}。只回复该编号。", "simple", [first]),
                ("刚才的批次编号是什么？只回复编号。", "simple", [first]),
                (
                    f"记住里程碑编号 {second}。另外，我胸痛且呼吸困难，是否需要立即就医？",
                    "strong",
                    [],
                ),
                (
                    "仅提取之前给出的批次编号和里程碑编号，不讨论其他话题。",
                    "simple",
                    [first, second],
                ),
            ]
        result.append(
            {
                "id": f"conversation-{index:02d}",
                "turns": turns,
                "variant": "generated_identifiers",
            }
        )
    return result


def final_answer(events):
    """Extract the complete user-facing answer from an ADK event sequence."""
    from google.adk.events.event import Event

    for value in reversed(events):
        event = Event.model_validate(value)
        if event.is_final_response() and event.content:
            text = "".join(
                part.text
                for part in event.content.parts or []
                if part.text and not part.thought
            ).strip()
            if text:
                return text
    return ""
