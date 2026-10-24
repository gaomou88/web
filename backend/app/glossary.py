"""经济数据中文释义：按事件名称关键词匹配。

每项：(正则, 中文名, 含义, 对本国货币通常的影响)
影响：up = 实际值高于预期通常利好该国货币；down = 高于预期通常利空；None = 视情况而定。
"""
from __future__ import annotations

import re
from typing import Any

ENTRIES: list[tuple[str, str, str, str | None]] = [
    (r"adp non-?farm", "ADP 就业人数变化", "私营机构 ADP 根据工资发放数据统计的私营部门新增就业，通常在官方非农前两天公布，被当作非农的前瞻参考。", "up"),
    (r"non-?farm (employment change|payrolls)", "非农就业人数变化", "上月除农业外新增的就业岗位数，是衡量美国就业市场最重要的指标，就业强通常意味着经济和消费有支撑、美联储更可能维持紧缩。", "up"),
    (r"unemployment claims|jobless claims", "初请失业金人数", "过去一周首次申请失业救济的人数，越少说明裁员越少、就业市场越好；每周公布，是最及时的就业数据。", "down"),
    (r"unemployment rate", "失业率", "在找工作但没有工作的人占劳动力的比例，越低说明就业越充分。", "down"),
    (r"claimant count", "申请失业金人数变化", "英国当月申请失业救济人数的变化，越少越好。", "down"),
    (r"employment change", "就业人数变化", "当期新增就业人数，越多说明就业市场越强。", "up"),
    (r"average (hourly )?earnings|wage", "平均时薪 / 薪资增长", "工资增长速度，增长快会推高消费和通胀压力，央行更倾向于加息或推迟降息。", "up"),
    (r"core pce", "核心 PCE 物价指数", "剔除食品和能源后的个人消费支出价格变化，是美联储最看重的通胀指标。高于预期意味着通胀压力大、降息推迟。", "up"),
    (r"\bpce price", "PCE 物价指数", "个人消费支出价格变化，衡量居民实际购买商品和服务的通胀水平。", "up"),
    (r"core cpi", "核心 CPI", "剔除食品和能源价格后的消费者物价变化，反映更持久的通胀趋势，央行决策的重要依据。", "up"),
    (r"\bcpi\b|consumer price", "消费者物价指数（CPI）", "居民购买的一篮子商品和服务的价格变化，是最常用的通胀指标。通胀高于预期时央行更可能加息或维持高利率。", "up"),
    (r"\bppi\b|producer price", "生产者物价指数（PPI）", "企业出厂价格的变化，被视为消费者通胀的先行指标。", "up"),
    (r"import prices", "进口价格指数", "进口商品价格的变化，会传导到国内物价。", "up"),
    (r"inflation expectations", "通胀预期", "居民或机构对未来通胀的预期，预期过高会让央行更警惕。", "up"),
    (r"\bgdp\b|gross domestic", "国内生产总值（GDP）", "一个经济体在一段时间内生产的全部商品和服务的价值，衡量经济增长速度。初值、修正值、终值依次公布。", "up"),
    (r"core retail", "核心零售销售", "剔除汽车（及汽油）后的零售销售，更能反映基础消费趋势。", "up"),
    (r"retail sales", "零售销售", "零售商的销售总额变化，反映居民消费，消费通常占经济的很大比重。", "up"),
    (r"ism manufacturing pmi", "ISM 制造业 PMI", "美国供应管理协会对制造业采购经理的调查，高于 50 表示扩张，低于 50 表示收缩。", "up"),
    (r"ism services pmi|ism non-?manufacturing", "ISM 服务业 PMI", "美国服务业采购经理调查，高于 50 表示扩张。服务业占美国经济大头，很受关注。", "up"),
    (r"manufacturing pmi", "制造业 PMI", "采购经理人指数，高于 50 表示制造业扩张，低于 50 表示收缩，是经济的先行指标。", "up"),
    (r"services pmi", "服务业 PMI", "服务业采购经理人指数，高于 50 表示扩张。", "up"),
    (r"composite pmi", "综合 PMI", "制造业和服务业 PMI 的加权，反映整体经济活动。", "up"),
    (r"\bpmi\b", "采购经理人指数（PMI）", "对企业采购经理的调查，50 为荣枯线，高于 50 表示扩张。", "up"),
    (r"federal funds rate|fomc statement|fomc", "美联储利率决议", "美联储联邦公开市场委员会决定基准利率。加息或释放偏鹰信号通常利好美元，降息或偏鸽利空美元。", "up"),
    (r"fomc (meeting )?minutes", "美联储会议纪要", "上次议息会议的详细讨论记录，可以看出委员们对后续利率路径的倾向。", None),
    (r"(fed )?chair .*speaks|powell", "美联储主席讲话", "美联储主席的公开讲话，市场从中寻找未来利率政策的线索。", None),
    (r"main refinancing rate|ecb (press conference|monetary policy)", "欧洲央行利率决议", "欧洲央行决定欧元区基准利率，加息利好欧元。", "up"),
    (r"official bank rate|boe|monetary policy summary|mpc", "英国央行利率决议", "英格兰银行决定英国基准利率。", "up"),
    (r"boj policy rate|monetary policy statement.*jpy|boj", "日本央行利率决议", "日本央行决定政策利率和收益率曲线控制等措施。", "up"),
    (r"overnight rate|boc rate", "加拿大央行利率决议", "加拿大央行决定隔夜拆借利率。", "up"),
    (r"cash rate|rba", "澳洲联储利率决议", "澳大利亚储备银行决定现金利率。", "up"),
    (r"official cash rate|rbnz", "新西兰联储利率决议", "新西兰储备银行决定官方现金利率。", "up"),
    (r"snb policy rate|libor rate", "瑞士央行利率决议", "瑞士国家银行决定政策利率。", "up"),
    (r"loan prime rate|\blpr\b", "贷款市场报价利率（LPR）", "中国银行贷款的定价基准，下调意味着货币政策放松。", "up"),
    (r"consumer confidence|consumer sentiment", "消费者信心指数", "对居民的调查，反映他们对经济和个人财务的看法，信心强通常意味着消费会增加。", "up"),
    (r"business confidence|ifo|zew", "企业信心 / 景气指数", "对企业或分析师的调查，反映对当前和未来经济的看法，是先行指标。", "up"),
    (r"trade balance", "贸易差额", "出口减进口。顺差扩大（数值变大）通常意味着对本币的需求增加。", "up"),
    (r"current account", "经常账户", "包括贸易、服务、收入和转移在内的对外收支，盈余通常对本币有支撑。", "up"),
    (r"building permits", "营建许可", "新批准的住宅建造许可数量，是房地产活动的先行指标。", "up"),
    (r"housing starts", "新屋开工", "当月开始建造的新住宅数量，反映房地产景气。", "up"),
    (r"existing home sales|new home sales|pending home sales|home sales", "房屋销售", "住宅销售数量，反映房地产市场和居民购买力。", "up"),
    (r"durable goods", "耐用品订单", "使用 3 年以上商品（如设备、汽车、飞机）的新订单，反映企业投资意愿。", "up"),
    (r"industrial production", "工业产出", "工厂、矿业和公用事业的产出变化。", "up"),
    (r"factory orders", "工厂订单", "制造业新订单的变化。", "up"),
    (r"jolts|job openings", "JOLTS 职位空缺", "企业的职位空缺数，衡量劳动力需求。", "up"),
    (r"crude oil inventories", "EIA 原油库存", "美国商业原油库存变化，库存增加通常利空油价。对加元等商品货币有间接影响。", None),
    (r"natural gas storage", "天然气库存", "美国天然气库存变化。", None),
    (r"bank holiday|holiday", "银行假日", "该国银行和多数金融市场休市，当天流动性通常较低。", None),
    (r"empire state|philly fed|richmond|chicago pmi|kansas", "地区制造业指数", "地区联储对当地制造业的调查，正值表示扩张，是全国数据的先行参考。", "up"),
    (r"treasury currency report|budget|federal budget", "财政预算 / 报告", "政府收支或财政相关报告。", None),
    (r"bond auction|auction", "国债拍卖", "国债发行拍卖的中标收益率和认购倍数，反映市场对国债的需求。", None),
    (r"speaks|testifies|press conference", "官员讲话", "央行或政府官员的公开讲话，市场从中寻找政策信号。", None),
]
_COMPILED = [(re.compile(p, re.I), zh, desc, eff) for p, zh, desc, eff in ENTRIES]

SUFFIX = [(r"\bm/m\b", "（环比）"), (r"\by/y\b", "（同比）"), (r"\bq/q\b", "（季度环比）"), (r"\bq/y\b", "（同比）"), (r"\bflash\b|\bprelim", "（初值）"),
          (r"\bfinal\b", "（终值）"), (r"\brevised\b", "（修正值）"), (r"\badvance\b", "（初值）")]


def explain(title: str) -> dict[str, Any]:
    for rx, zh, desc, eff in _COMPILED:
        if rx.search(title):
            extra = "".join(z for p, z in SUFFIX if re.search(p, title, re.I))
            return {"name_zh": zh + extra, "desc": desc, "effect": eff}
    return {"name_zh": "", "desc": "", "effect": None}
