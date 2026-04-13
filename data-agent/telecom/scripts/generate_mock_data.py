"""
Mock 数据生成模块 — 内部模块，由 scripts/1_generate_data.py 调用。

不要直接运行此文件。
"""

import json
import random
import uuid
from datetime import datetime, timedelta

import numpy as np

random.seed(42)
np.random.seed(42)

# Reference "now" for all timestamps
NOW = datetime(2025, 3, 29, 12, 0, 0)
TS_FMT = "%Y-%m-%d %H:%M:%S"

# ---------------------------------------------------------------------------
# Region / city definitions
# ---------------------------------------------------------------------------
REGIONS = {
    "华北": ["北京", "天津", "石家庄", "太原", "呼和浩特"],
    "华东": ["上海", "南京", "杭州", "合肥", "济南"],
    "华南": ["广州", "深圳", "厦门", "南宁", "海口"],
    "西南": ["成都", "重庆", "昆明", "贵阳", "拉萨"],
    "东北": ["沈阳", "长春", "哈尔滨", "大连", "吉林"],
}

CITY_CODES = {
    "北京": "BJ", "天津": "TJ", "石家庄": "SJZ", "太原": "TY", "呼和浩特": "HHHT",
    "上海": "SH", "南京": "NJ", "杭州": "HZ", "合肥": "HF", "济南": "JN",
    "广州": "GZ", "深圳": "SZ", "厦门": "XM", "南宁": "NN", "海口": "HK",
    "成都": "CD", "重庆": "CQ", "昆明": "KM", "贵阳": "GY", "拉萨": "LS",
    "沈阳": "SY", "长春": "CC", "哈尔滨": "HRB", "大连": "DL", "吉林": "JL",
}

# Approximate WGS84 coordinates
CITY_COORDS = {
    "北京": (116.4074, 39.9042), "天津": (117.1907, 39.1256),
    "石家庄": (114.5149, 38.0428), "太原": (112.5489, 37.8706),
    "呼和浩特": (111.7510, 40.8427),
    "上海": (121.4737, 31.2304), "南京": (118.7969, 32.0603),
    "杭州": (120.1551, 30.2741), "合肥": (117.2272, 31.8206),
    "济南": (117.1205, 36.6510),
    "广州": (113.2644, 23.1291), "深圳": (114.0579, 22.5431),
    "厦门": (118.0894, 24.4798), "南宁": (108.3661, 22.8170),
    "海口": (110.3493, 20.0174),
    "成都": (104.0657, 30.5728), "重庆": (106.5516, 29.5630),
    "昆明": (102.8329, 25.0389), "贵阳": (106.6302, 26.6477),
    "拉萨": (91.1322, 29.6604),
    "沈阳": (123.4315, 41.8057), "长春": (125.3245, 43.8868),
    "哈尔滨": (126.5340, 45.8038), "大连": (121.6147, 38.9140),
    "吉林": (126.5496, 43.8378),
}

CITY_PROVINCE = {
    "北京": "北京", "天津": "天津", "石家庄": "河北", "太原": "山西", "呼和浩特": "内蒙古",
    "上海": "上海", "南京": "江苏", "杭州": "浙江", "合肥": "安徽", "济南": "山东",
    "广州": "广东", "深圳": "广东", "厦门": "福建", "南宁": "广西", "海口": "海南",
    "成都": "四川", "重庆": "重庆", "昆明": "云南", "贵阳": "贵州", "拉萨": "西藏",
    "沈阳": "辽宁", "长春": "吉林", "哈尔滨": "黑龙江", "大连": "辽宁", "吉林": "吉林",
}

REGION_NUM = {"华北": 1, "华东": 2, "华南": 3, "西南": 4, "东北": 5}

CUSTOMER_NAMES = [
    "Acme银行", "MediaCorp", "华夏保险", "东方证券", "中天物流",
    "博联科技", "信达通信", "龙翔能源", "国泰航空", "恒信地产",
    "华创医疗", "九州教育", "明珠零售", "鹏程制造", "瑞丰农业",
    "盛世游戏", "天元金融", "万利电商", "新纪元IT", "远景新能源",
    "紫光半导体", "中科云计算", "蓝海大数据", "金桥外贸", "亿达物联",
    "启明星辰安全", "浩瀚传媒", "鼎盛化工", "长城汽车", "锦绣文旅",
]

# Pre-generated customer UUIDs (30 customers, indexed 0-29)
CUSTOMER_UUIDS = [str(uuid.uuid4()) for _ in range(30)]


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _ts(dt: datetime) -> str:
    return dt.strftime(TS_FMT)


def _rand_date(start_year: int = 2022, end_year: int = 2025) -> str:
    d = datetime(start_year, 1, 1) + timedelta(
        days=random.randint(0, (end_year - start_year) * 365)
    )
    return d.strftime("%Y-%m-%d")


def _rand_future_date(start_year: int = 2026, end_year: int = 2030) -> str:
    d = datetime(start_year, 1, 1) + timedelta(
        days=random.randint(0, (end_year - start_year) * 365)
    )
    return d.strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# t_site  (25 rows)
# ---------------------------------------------------------------------------

def _generate_sites():
    rows = []
    # Pre-assign site types to ensure at least 5 DC
    # We'll use a deterministic pattern: first city per region = DC
    site_types_pool = ["DC"] * 5 + ["POP"] * 10 + ["CO"] * 8 + ["COLO"] + ["EDGE"]
    random.shuffle(site_types_pool)

    # Ensure at least 5 DC
    dc_count = sum(1 for s in site_types_pool if s == "DC")
    while dc_count < 5:
        idx = next(i for i, s in enumerate(site_types_pool) if s != "DC")
        site_types_pool[idx] = "DC"
        dc_count += 1

    # Status: 22 ACTIVE, 2 DECOMMISSIONED, 1 PLANNED
    statuses = ["ACTIVE"] * 22 + ["DECOMMISSIONED"] * 2 + ["PLANNED"]
    random.shuffle(statuses)

    # Tier assignment: ensure each region has at least 1 TIER1
    tiers = []
    all_cities = []
    for region, cities in REGIONS.items():
        for city in cities:
            all_cities.append((region, city))

    # First city of each region -> TIER1
    tier_map = {}
    for region, cities in REGIONS.items():
        tier_map[cities[0]] = "TIER1"

    # Remaining: mix of TIER1/TIER2/TIER3
    remaining_tiers = ["TIER1"] * 3 + ["TIER2"] * 10 + ["TIER3"] * 7
    random.shuffle(remaining_tiers)
    rt_idx = 0
    for region, city in all_cities:
        if city not in tier_map:
            tier_map[city] = remaining_tiers[rt_idx]
            rt_idx += 1

    operators = ["中国电信", "万国数据", "中国联通", "中国移动", "世纪互联"]
    cooling_types = ["AIR", "LIQUID", "HYBRID"]

    for i, (region, city) in enumerate(all_cities):
        code = CITY_CODES[city]
        site_id = str(uuid.uuid4())
        site_type = site_types_pool[i]
        tier = tier_map[city]
        lng, lat = CITY_COORDS[city]
        status = statuses[i]

        total_racks = random.choice([48, 96, 120, 200, 300]) if site_type == "DC" else random.choice([12, 24, 36, 48])
        used_racks = int(total_racks * random.uniform(0.4, 0.9))
        power_kw = round(total_racks * random.uniform(5, 12), 2)

        rows.append((
            site_id,
            f"{city}{site_type}-01",
            f"{code}-{site_type}01",
            site_type,
            region,
            CITY_PROVINCE[city],
            city,
            f"{city}经济技术开发区XX路XX号",
            round(lng, 7),
            round(lat, 7),
            tier,
            total_racks,
            used_racks,
            power_kw,
            random.choice(cooling_types),
            random.choice(operators),
            f"张工{i+1:02d}",
            f"138{random.randint(10000000, 99999999)}",
            _rand_date(2020, 2024),
            _rand_future_date(2027, 2032),
            status,
            f"{city}站点备注",
        ))

    return rows


# ---------------------------------------------------------------------------
# t_network_element  (50 rows)
# ---------------------------------------------------------------------------

def _generate_network_elements(sites):
    """Return (rows, ne_list) where ne_list is list of dicts with metadata."""
    # Build site lookup
    site_ids = [s[0] for s in sites]  # site_id at index 0

    # We need 50 NEs distributed across 25 sites (1-4 per site)
    # Ensure every site gets at least 1 NE, then distribute remaining 25
    ne_per_site = [1] * 25
    remaining = 25
    while remaining > 0:
        idx = random.randint(0, 24)
        if ne_per_site[idx] < 4:
            ne_per_site[idx] += 1
            remaining -= 1

    # Role distribution: ~20 PE, ~10 P, ~15 CE, ~3 RR, ~2 ASBR
    roles = ["PE"] * 20 + ["P"] * 10 + ["CE"] * 15 + ["RR"] * 3 + ["ASBR"] * 2
    random.shuffle(roles)

    # Vendor distribution: ~25 HUAWEI, ~15 CISCO, ~5 ZTE, ~5 JUNIPER
    vendors = ["HUAWEI"] * 25 + ["CISCO"] * 15 + ["ZTE"] * 5 + ["JUNIPER"] * 5
    random.shuffle(vendors)

    model_map = {
        "HUAWEI": ["NE40E-X16A", "NE5000E"],
        "CISCO": ["ASR9000", "NCS5500"],
        "ZTE": ["ZXR10-M6000"],
        "JUNIPER": ["MX960"],
    }
    sw_map = {
        "HUAWEI": "V800R023C10",
        "CISCO": "IOS-XR 7.7.2",
        "ZTE": "V5.00.10",
        "JUNIPER": "Junos 23.2R1",
    }

    rows = []
    ne_list = []  # metadata for FK references
    ne_idx = 0
    role_counter = {}  # per-city role counter

    for site_i, count in enumerate(ne_per_site):
        site_id = site_ids[site_i]
        site_row = sites[site_i]
        region = site_row[4]  # region
        city = site_row[6]    # city
        code = CITY_CODES[city]
        region_n = REGION_NUM[region]

        for j in range(count):
            role = roles[ne_idx]
            vendor = vendors[ne_idx]
            model = random.choice(model_map[vendor])

            # Role counter for this city
            role_counter.setdefault(code, {})
            role_counter[code].setdefault(role, 0)
            role_counter[code][role] += 1
            seq = role_counter[code][role]

            ne_id = str(uuid.uuid4())
            ne_name = f"{code}-CORE-{role}{seq:02d}"
            management_ip = f"10.{region_n}.{site_i+1}.{j+1}"
            loopback_ipv4 = f"1.1.{ne_idx+1}.1" if role in ("PE", "P") else None
            loopback_ipv6 = f"2001:DB8:{ne_idx+1:X}::1" if role in ("PE", "P") else None
            router_id = loopback_ipv4

            # SRv6: all PE + some P (total ~30)
            srv6_enabled = role == "PE" or (role == "P" and random.random() < 0.8)
            mpls_enabled = role in ("PE", "P")

            # oper_status: 45 UP, 3 DOWN, 2 DEGRADED
            if ne_idx < 45:
                oper_status = "UP"
            elif ne_idx < 48:
                oper_status = "DOWN"
            else:
                oper_status = "DEGRADED"

            # admin_status: 48 UP, 2 DOWN
            admin_status = "UP" if ne_idx < 48 else "DOWN"

            srv6_locator = f"2001:DB8:{ne_idx+1:X}00::/48" if srv6_enabled else None
            isis_sys_id = f"0100.0000.{ne_idx+1:04d}"
            isis_area_id = f"49.{region_n:04d}"

            rows.append((
                ne_id, ne_name, "ROUTER", vendor, model,
                sw_map[vendor],
                f"SPC{random.randint(100,999)}",
                role, management_ip,
                loopback_ipv4, loopback_ipv6,
                router_id,
                65000,
                isis_sys_id, isis_area_id,
                srv6_locator,
                mpls_enabled, srv6_enabled,
                random.random() < 0.8,  # netconf_enabled
                random.random() < 0.7,  # telemetry_enabled
                site_id,
                f"A{random.randint(1,10):02d}-U{random.randint(1,42):02d}",
                f"210235{random.randint(1000000000, 9999999999)}",
                f"ASSET-2024-{ne_idx+1:05d}",
                _rand_date(2022, 2025),
                _rand_future_date(2026, 2029),
                admin_status, oper_status,
                f"{city} {role} 设备",
                _ts(NOW - timedelta(days=random.randint(30, 365))),
                _ts(NOW - timedelta(hours=random.randint(1, 48))),
            ))

            ne_list.append({
                "ne_id": ne_id,
                "site_id": site_id,
                "role": role,
                "vendor": vendor,
                "srv6_enabled": srv6_enabled,
                "mpls_enabled": mpls_enabled,
                "oper_status": oper_status,
                "city_code": code,
                "ne_idx": ne_idx,
                "region": region,
            })
            ne_idx += 1

    return rows, ne_list


# ---------------------------------------------------------------------------
# t_board  (150 rows)
# ---------------------------------------------------------------------------

def _generate_boards(ne_list):
    rows = []
    board_list = []
    for i, ne in enumerate(ne_list):
        ne_id = ne["ne_id"]
        for j in range(3):
            board_id = str(uuid.uuid4())
            board_type = "MPU" if j == 0 else "LPU"
            slot = f"{j*2+1}/0"

            # 5% FAULT
            oper_status = "FAULT" if random.random() < 0.05 else "UP"

            board_name = "CR5DMPUA10" if board_type == "MPU" else f"CR5D00L4XF{random.choice([90, 60, 40])}"
            port_count = 0 if board_type == "MPU" else random.choice([4, 8, 16, 36])
            port_type = None if board_type == "MPU" else random.choice(["100GE", "400GE", "10GE"])
            fwd_cap = None if board_type == "MPU" else round(random.uniform(600, 3600), 2)
            mem_total = random.choice([16384, 32768])

            rows.append((
                board_id, ne_id, slot, board_type, board_name,
                "VER.B", f"V{random.randint(200,300)}R{random.randint(1,5):03d}",
                f"21023{random.randint(1000000000, 9999999999)}",
                port_count, port_type,
                fwd_cap, mem_total,
                round(random.uniform(70, 90), 2),
                round(random.uniform(100, 900), 2),
                "UP", oper_status,
                _rand_date(2022, 2025),
                _ts(NOW - timedelta(days=random.randint(1, 90))) if random.random() < 0.3 else None,
                random.randint(1000, 20000),
                f"{board_type}板卡",
                _ts(NOW - timedelta(days=random.randint(30, 365))),
                _ts(NOW - timedelta(hours=random.randint(1, 48))),
            ))
            board_list.append({"board_id": board_id, "ne_id": ne_id, "board_type": board_type})

    return rows, board_list


# ---------------------------------------------------------------------------
# t_interface  (500 rows)
# ---------------------------------------------------------------------------

def _generate_interfaces(ne_list, board_list):
    rows = []
    if_list = []  # metadata for FK references
    if_seq = 0

    # Build board lookup by ne_id (only LPU boards)
    boards_by_ne = {}
    for b in board_list:
        if b["board_type"] == "LPU":
            boards_by_ne.setdefault(b["ne_id"], []).append(b["board_id"])

    # Distribution targets: ~300 PHYSICAL, ~80 ETH-TRUNK, ~50 LOOPBACK, ~40 VLANIF, ~30 TUNNEL
    # 500 / 50 NEs = 10 per NE
    phy_types = ["GE", "10GE", "25GE", "100GE", "400GE"]
    speed_map = {"GE": 1000, "10GE": 10000, "25GE": 25000, "100GE": 100000, "400GE": 400000}

    # CRITICAL for Q05: At least 2 NEs with >10 100GE PHYSICAL interfaces
    # We pick 2 PE NEs to get 12 100GE each -- these NEs will get more interfaces
    pe_nes = [ne for ne in ne_list if ne["role"] == "PE"]
    q05_nes = set()
    if len(pe_nes) >= 2:
        q05_nes = {pe_nes[0]["ne_id"], pe_nes[1]["ne_id"]}

    for ne in ne_list:
        ne_id = ne["ne_id"]
        ne_boards = boards_by_ne.get(ne_id, [])

        # Determine interface count for this NE
        if ne_id in q05_nes:
            n_ifs = 16  # More interfaces to accommodate 12+ 100GE
        else:
            n_ifs = 10

        for j in range(n_ifs):
            if_seq += 1
            if_id = str(uuid.uuid4())

            # Assign type
            if ne_id in q05_nes and j < 12:
                # First 12 are 100GE PHYSICAL for Q05
                if_type = "PHYSICAL"
                phy_type = "100GE"
            elif j < 6:
                if_type = "PHYSICAL"
                phy_type = random.choice(phy_types)
            elif j < 8:
                if_type = random.choice(["ETH-TRUNK", "LOOPBACK"])
                phy_type = None
            elif j < 9:
                if_type = random.choice(["VLANIF", "TUNNEL"])
                phy_type = None
            else:
                if_type = random.choice(["PHYSICAL", "ETH-TRUNK", "LOOPBACK", "VLANIF", "TUNNEL"])
                phy_type = random.choice(phy_types) if if_type == "PHYSICAL" else None

            speed = speed_map.get(phy_type) if phy_type else (
                random.choice([1000, 10000, 100000]) if if_type == "ETH-TRUNK" else None
            )
            mtu = 9216 if if_type in ("PHYSICAL", "ETH-TRUNK") else 1500
            board_id = random.choice(ne_boards) if ne_boards and if_type == "PHYSICAL" else None

            # IP addressing
            ipv4 = f"192.168.{ne['ne_idx']}.{j+1}" if if_type in ("PHYSICAL", "VLANIF", "LOOPBACK") else None
            ipv4_mask = "255.255.255.252" if ipv4 else None
            ipv6 = f"2001:DB8:{ne['ne_idx']:X}::{j+1}" if if_type in ("PHYSICAL", "LOOPBACK") else None
            ipv6_prefix = 126 if ipv6 else None

            mac = f"00:11:22:{ne['ne_idx']:02X}:{j:02X}:01" if if_type == "PHYSICAL" else None

            # Name
            if if_type == "PHYSICAL" and phy_type:
                if_name = f"{phy_type}{j//4}/{0}/{j%4}"
            elif if_type == "ETH-TRUNK":
                if_name = f"Eth-Trunk{j}"
            elif if_type == "LOOPBACK":
                if_name = f"LoopBack{j-6 if j > 6 else 0}"
            elif if_type == "VLANIF":
                if_name = f"Vlanif{100+j}"
            else:
                if_name = f"Tunnel{j}"

            # Status: 95% UP
            admin_status = "UP" if random.random() < 0.95 else "DOWN"
            oper_status = "UP" if random.random() < 0.95 else "DOWN"

            vlan_id = random.randint(100, 4000) if if_type == "VLANIF" else None
            vrf_name = None  # will be set by VRF binding

            rows.append((
                if_id, ne_id, board_id,
                if_name,
                if_seq,  # if_index
                if_type, phy_type, speed, mtu,
                ipv4, ipv4_mask, ipv6, ipv6_prefix,
                mac,
                vlan_id, vrf_name,
                None,  # trunk_id
                None,  # trunk_member_count
                if_type == "PHYSICAL",  # isis_enabled
                random.randint(10, 100) if if_type == "PHYSICAL" else None,  # isis_cost
                if_type == "PHYSICAL",  # ospf_enabled
                random.random() < 0.5,  # bfd_enabled
                random.choice(["GOLD-INGRESS", "SILVER-EGRESS", "PLATINUM-CORE", None]),
                admin_status, oper_status,
                _ts(NOW - timedelta(hours=random.randint(1, 720))) if random.random() < 0.3 else None,
                f"接口描述-{ne_id}-{if_name}",
                _ts(NOW - timedelta(days=random.randint(30, 365))),
                _ts(NOW - timedelta(hours=random.randint(1, 48))),
            ))

            if_list.append({
                "if_id": if_id,
                "ne_id": ne_id,
                "if_type": if_type,
                "phy_type": phy_type,
                "speed_mbps": speed,
                "oper_status": oper_status,
            })

    return rows, if_list


# ---------------------------------------------------------------------------
# t_physical_link  (100 rows)
# ---------------------------------------------------------------------------

def _generate_physical_links(ne_list, if_list, vpn_list_for_links=None):
    """Generate physical links.

    vpn_list_for_links: list of GOLD VPN ids (used for Q12 constraint later).
    """
    rows = []
    link_list = []

    # Build lookup: NE -> list of PHYSICAL interfaces
    phy_ifs_by_ne = {}
    for iface in if_list:
        if iface["if_type"] == "PHYSICAL":
            phy_ifs_by_ne.setdefault(iface["ne_id"], []).append(iface["if_id"])

    # NE lookup
    ne_lookup = {ne["ne_id"]: ne for ne in ne_list}

    # Get NE pairs for links
    ne_ids_with_phy = [ne_id for ne_id in phy_ifs_by_ne if len(phy_ifs_by_ne[ne_id]) > 0]

    used_if_ids = set()
    link_seq = 0

    # We need 100 links. ~20% intra-site, ~80% inter-site
    # First generate inter-site links
    for _ in range(100):
        # Pick two NEs
        attempts = 0
        while attempts < 50:
            a_ne_id = random.choice(ne_ids_with_phy)
            b_ne_id = random.choice(ne_ids_with_phy)
            if a_ne_id == b_ne_id:
                attempts += 1
                continue

            # Find available interfaces
            a_avail = [x for x in phy_ifs_by_ne[a_ne_id] if x not in used_if_ids]
            b_avail = [x for x in phy_ifs_by_ne[b_ne_id] if x not in used_if_ids]
            if not a_avail or not b_avail:
                attempts += 1
                continue
            break
        else:
            continue

        a_if_id = random.choice(a_avail)
        b_if_id = random.choice(b_avail)
        used_if_ids.add(a_if_id)
        used_if_ids.add(b_if_id)

        link_seq += 1
        link_id = str(uuid.uuid4())

        a_ne = ne_lookup[a_ne_id]
        b_ne = ne_lookup[b_ne_id]
        is_intra = a_ne["site_id"] == b_ne["site_id"]

        bandwidth = random.choice([10000, 100000])
        distance = round(random.uniform(0.1, 2.0), 2) if is_intra else round(random.uniform(50, 2500), 2)
        latency = round(distance * 0.005, 3)

        # 5% DOWN
        oper_status = "DOWN" if random.random() < 0.05 else "UP"

        a_code = a_ne["city_code"]
        b_code = b_ne["city_code"]

        rows.append((
            link_id,
            f"{a_code}-{a_ne['role']}{link_seq:02d}<->{b_code}-{b_ne['role']}{link_seq:02d}",
            "FIBER",
            a_ne_id, a_if_id, a_ne["site_id"],
            b_ne_id, b_if_id, b_ne["site_id"],
            bandwidth, distance, latency,
            random.choice([12, 24, 48]),
            random.choice([1310, 1550]),
            f"CAB-{a_code}-{b_code}-{link_seq:03d}",
            is_intra,
            random.choice(["NONE", "1+1", "1:1"]),
            random.choice(["中国电信", "中国联通", None]),
            f"CIR-{20240000+link_seq}",
            random.choice(["GOLD", "SILVER", "BRONZE"]),
            "UP", oper_status,
            _rand_date(2022, 2025),
            _rand_future_date(2026, 2030),
            round(random.uniform(5000, 80000), 2) if not is_intra else 0.0,
            f"链路备注-{link_id}",
            _ts(NOW - timedelta(days=random.randint(30, 365))),
            _ts(NOW - timedelta(hours=random.randint(1, 48))),
        ))

        link_list.append({
            "link_id": link_id,
            "a_ne_id": a_ne_id,
            "z_ne_id": b_ne_id,
            "a_site_id": a_ne["site_id"],
            "z_site_id": b_ne["site_id"],
            "oper_status": oper_status,
        })

    return rows, link_list


# ---------------------------------------------------------------------------
# t_vrf_instance  (120 rows)
# ---------------------------------------------------------------------------

def _generate_vrf_instances(ne_list):
    rows = []
    vrf_list = []
    vrf_seq = 0
    pe_nes = [ne for ne in ne_list if ne["role"] == "PE"]

    # We need ~120 VRFs across ~20 PEs => 6 per PE on average
    # Use 5-7 per PE to reach ~120
    for ne in pe_nes:
        n_vrfs = random.choice([5, 6, 6, 6, 7])  # 5-7 per PE to reach ~120 total
        for j in range(n_vrfs):
            vrf_seq += 1
            vrf_id = str(uuid.uuid4())
            cust_name = CUSTOMER_NAMES[(vrf_seq - 1) % len(CUSTOMER_NAMES)]
            vrf_name = f"vpn_{cust_name.lower().replace(' ', '_')}"

            rd = f"65000:{vrf_seq}"
            rt_import = f"65000:{vrf_seq}"
            rt_export = f"65000:{vrf_seq}"

            admin_status = "DOWN" if random.random() < 0.05 else "UP"
            oper_status = admin_status

            srv6_loc = f"2001:DB8:{ne['ne_idx']+1:X}00::/48" if ne["srv6_enabled"] else None
            srv6_dt4 = f"2001:DB8:{ne['ne_idx']+1:X}00::{vrf_seq}" if ne["srv6_enabled"] else None
            srv6_dt6 = f"2001:DB8:{ne['ne_idx']+1:X}00::F{vrf_seq}" if ne["srv6_enabled"] else None

            max_routes = random.choice([5000, 10000, 20000])
            current_routes = random.randint(100, max_routes // 2)

            rows.append((
                vrf_id, ne["ne_id"], vrf_name, rd,
                rt_import, rt_export,
                random.choice(["IPV4", "IPV6", "DUAL"]),
                random.choice(["PER_INSTANCE", "PER_ROUTE"]),
                random.choice(["TP-SRV6-TE", "TP-LDP", "TP-SRV6-BE"]),
                srv6_loc, srv6_dt4, srv6_dt6,
                random.choice(["NONE", "L3"]),
                max_routes, current_routes,
                random.randint(1, 8),
                CUSTOMER_UUIDS[(vrf_seq-1) % 30],
                cust_name,
                random.choice(["MPLS_VPN", "CLOUD_CONNECT", "INTERNET"]),
                admin_status, oper_status,
                f"{cust_name} VRF on {ne['ne_id']}",
                _ts(NOW - timedelta(days=random.randint(30, 365))),
                _ts(NOW - timedelta(hours=random.randint(1, 48))),
            ))

            vrf_list.append({
                "vrf_id": vrf_id,
                "ne_id": ne["ne_id"],
                "vrf_name": vrf_name,
                "customer_name": cust_name,
            })

    return rows, vrf_list


# ---------------------------------------------------------------------------
# t_l3vpn_service  (30 rows)
# ---------------------------------------------------------------------------

def _generate_l3vpn_services():
    rows = []
    vpn_list = []

    # Service level distribution: 6 PLATINUM, 6 GOLD, 10 SILVER, 8 BRONZE
    levels = ["PLATINUM"] * 6 + ["GOLD"] * 6 + ["SILVER"] * 10 + ["BRONZE"] * 8
    random.shuffle(levels)

    # CRITICAL Q06: At least 3 with underlay_type='SRV6_TE' and admin_status='ACTIVE'
    underlay_types = ["SRV6_TE"] * 8 + ["SRV6_BE"] * 8 + ["MPLS_LDP"] * 8 + ["MPLS_TE"] * 6
    random.shuffle(underlay_types)

    for i in range(30):
        vpn_seq = i + 1
        vpn_id = str(uuid.uuid4())
        level = levels[i]
        cust_name = CUSTOMER_NAMES[i % len(CUSTOMER_NAMES)]

        # Bandwidth based on level
        if level == "PLATINUM":
            bw = random.choice([5000, 10000, 20000])
        elif level == "GOLD":
            bw = random.choice([1000, 2000, 5000, 10000])
        elif level == "SILVER":
            bw = random.choice([100, 200, 500, 1000])
        else:
            bw = random.choice([10, 50, 100])

        underlay = underlay_types[i]

        # CRITICAL Q08: GOLD VPNs should have max_latency_ms set
        if level == "GOLD":
            max_latency = 20.0
            max_jitter = 5.0
            max_loss = 0.01
        elif level == "PLATINUM":
            max_latency = 10.0
            max_jitter = 2.0
            max_loss = 0.001
        elif level == "SILVER":
            max_latency = 50.0
            max_jitter = 10.0
            max_loss = 0.1
        else:
            max_latency = 100.0
            max_jitter = 20.0
            max_loss = 0.5

        # Ensure at least 3 SRV6_TE + ACTIVE for Q06
        if i < 3:
            underlay = "SRV6_TE"
            admin_status = "ACTIVE"
        else:
            admin_status = random.choice(["ACTIVE"] * 9 + ["SUSPENDED"])

        oper_status = "UP" if admin_status == "ACTIVE" else "DOWN"

        monthly_fee = round(bw * random.uniform(5, 20), 2)

        rows.append((
            vpn_id,
            f"{cust_name}-VPN",
            "L3VPN",
            random.choice(["ANY_TO_ANY", "HUB_SPOKE", "P2P"]),
            CUSTOMER_UUIDS[i % 30],
            cust_name,
            level,
            bw,
            round(max_latency, 3),
            round(max_jitter, 3),
            round(max_loss, 4),
            0,  # pe_count (will update)
            0,  # site_count
            underlay,
            random.random() < 0.2,  # encryption
            random.random() < 0.1,  # multicast
            f"65000:{vpn_seq+1000}",
            f"65000:{vpn_seq+1000}",
            _rand_date(2023, 2025),
            _rand_future_date(2026, 2030),
            monthly_fee,
            admin_status, oper_status,
            random.choice(["DEPLOYED", "DEPLOYED", "DEPLOYED", "DEPLOYING"]),
            _ts(NOW - timedelta(days=random.randint(1, 90))),
            f"{cust_name} L3VPN服务",
            _ts(NOW - timedelta(days=random.randint(30, 365))),
            _ts(NOW - timedelta(hours=random.randint(1, 48))),
        ))

        vpn_list.append({
            "vpn_id": vpn_id,
            "service_level": level,
            "admin_status": admin_status,
            "max_latency_ms": max_latency,
            "underlay_type": underlay,
            "customer_name": cust_name,
        })

    return rows, vpn_list


# ---------------------------------------------------------------------------
# t_vpn_pe_binding  (80 rows)
# ---------------------------------------------------------------------------

def _generate_vpn_pe_bindings(vpn_list, ne_list, vrf_list, if_list):
    rows = []
    binding_list = []
    bind_seq = 0

    pe_nes = [ne for ne in ne_list if ne["role"] == "PE"]
    # Build VRF lookup by ne_id
    vrfs_by_ne = {}
    for v in vrf_list:
        vrfs_by_ne.setdefault(v["ne_id"], []).append(v)

    # Build interface lookup by ne_id (PHYSICAL only for CE-facing)
    ifs_by_ne = {}
    for iface in if_list:
        if iface["if_type"] in ("PHYSICAL", "VLANIF"):
            ifs_by_ne.setdefault(iface["ne_id"], []).append(iface["if_id"])

    used_if_ids = set()

    for vpn in vpn_list:
        # Each VPN bound to 2-5 PEs
        n_bindings = random.randint(2, 5)
        chosen_pes = random.sample(pe_nes, min(n_bindings, len(pe_nes)))

        for pe in chosen_pes:
            ne_id = pe["ne_id"]
            # Find a VRF on this NE
            ne_vrfs = vrfs_by_ne.get(ne_id, [])
            if not ne_vrfs:
                continue
            vrf = random.choice(ne_vrfs)

            # Find an interface
            ne_ifs = ifs_by_ne.get(ne_id, [])
            avail_ifs = [x for x in ne_ifs if x not in used_if_ids]
            if not avail_ifs:
                avail_ifs = ne_ifs  # reuse if needed
            if not avail_ifs:
                continue
            chosen_if = random.choice(avail_ifs)
            used_if_ids.add(chosen_if)

            bind_seq += 1
            binding_id = str(uuid.uuid4())

            rows.append((
                binding_id,
                vpn["vpn_id"],
                ne_id,
                vrf["vrf_id"],
                chosen_if,
                random.choice(["HUB", "SPOKE", "SPOKE"]),
                f"192.168.{bind_seq}.2",
                f"192.168.{bind_seq}.1",
                None, None,
                random.choice([65100, 65200, 65300, None]),
                random.choice(["STATIC", "EBGP", "OSPF"]),
                random.choice([100, 1000, 10000]),
                random.randint(100, 4000),
                random.choice(["DOT1Q", "UNTAG", "QINQ"]),
                f"{vpn['customer_name']} {pe['city_code']}接入",
                "UP", "UP",
                f"绑定描述-{binding_id}",
                _ts(NOW - timedelta(days=random.randint(30, 365))),
                _ts(NOW - timedelta(hours=random.randint(1, 48))),
            ))

            binding_list.append({
                "binding_id": binding_id,
                "vpn_id": vpn["vpn_id"],
                "ne_id": ne_id,
                "vrf_id": vrf["vrf_id"],
                "if_id": chosen_if,
            })

            if bind_seq >= 80:
                break
        if bind_seq >= 80:
            break

    return rows, binding_list


# ---------------------------------------------------------------------------
# t_srv6_policy  (50 rows)
# ---------------------------------------------------------------------------

def _generate_srv6_policies(ne_list):
    rows = []
    policy_list = []

    pe_nes = [ne for ne in ne_list if ne["role"] == "PE"]
    srv6_pe_nes = [ne for ne in pe_nes if ne["srv6_enabled"]]

    # CRITICAL Q13: ~5 srv6-enabled PEs with NO policies
    # We pick policies from a subset of srv6_pe_nes
    if len(srv6_pe_nes) > 5:
        pes_with_policies = srv6_pe_nes[:-5]  # Last 5 get no policies
        pes_without_policies = srv6_pe_nes[-5:]
    else:
        pes_with_policies = srv6_pe_nes
        pes_without_policies = []

    # provision type distribution: ~17 STATIC, ~17 DYNAMIC, ~16 CONTROLLER
    provision_types = ["STATIC"] * 17 + ["DYNAMIC"] * 17 + ["CONTROLLER"] * 16
    random.shuffle(provision_types)

    sla_types = ["LOW_LATENCY", "LOW_JITTER", "HIGH_BW"]

    # CRITICAL Q03: At least 5 with oper_status='DOWN'
    oper_statuses = ["DOWN"] * 7 + ["UP"] * 40 + ["PARTIAL"] * 3
    random.shuffle(oper_statuses)

    for i in range(50):
        pol_seq = i + 1
        policy_id = str(uuid.uuid4())

        source_ne = random.choice(pes_with_policies) if pes_with_policies else random.choice(pe_nes)
        # Pick a different PE as destination
        dest_candidates = [ne for ne in pe_nes if ne["ne_id"] != source_ne["ne_id"]]
        dest_ne = random.choice(dest_candidates) if dest_candidates else source_ne

        color = random.choice([10, 20, 30, 50, 100])
        sla_type = random.choice(sla_types)

        segment_list = json.dumps([
            f"2001:DB8:{source_ne['ne_idx']+1:X}00::1",
            f"2001:DB8:{dest_ne['ne_idx']+1:X}00::1",
        ])

        max_lat = round(random.uniform(10, 50), 3) if sla_type == "LOW_LATENCY" else None
        max_jit = round(random.uniform(2, 10), 3) if sla_type == "LOW_JITTER" else None
        min_bw = random.choice([1000, 10000, 50000]) if sla_type == "HIGH_BW" else None

        rows.append((
            policy_id,
            f"SRv6-TE-{source_ne['city_code']}-{dest_ne['city_code']}-{sla_type}",
            source_ne["ne_id"],
            f"2001:DB8:{dest_ne['ne_idx']+1:X}00::1",
            dest_ne["ne_id"],
            color,
            0,  # distinguisher
            f"2001:DB8:{source_ne['ne_idx']+1:X}00::FF",
            random.choice([100, 200]),
            random.randint(1, 3),
            segment_list,
            random.random() < 0.4,
            provision_types[i],
            sla_type,
            max_lat, max_jit, min_bw,
            random.randint(2, 6),
            random.randint(0, 5),
            random.randint(1, 4),
            "UP" if oper_statuses[i] != "DOWN" else "UP",
            oper_statuses[i],
            random.choice(["NCE", "CLI", "PCEP"]),
            _ts(NOW - timedelta(hours=random.randint(1, 720))),
            f"SRv6 Policy {policy_id}",
            _ts(NOW - timedelta(days=random.randint(30, 365))),
            _ts(NOW - timedelta(hours=random.randint(1, 48))),
        ))

        policy_list.append({
            "policy_id": policy_id,
            "source_ne_id": source_ne["ne_id"],
            "dest_ne_id": dest_ne["ne_id"],
            "oper_status": oper_statuses[i],
        })

    return rows, policy_list


# ---------------------------------------------------------------------------
# t_tunnel  (80 rows)
# ---------------------------------------------------------------------------

def _generate_tunnels(ne_list, policy_list, vpn_list):
    rows = []
    tunnel_list = []

    pe_nes = [ne for ne in ne_list if ne["role"] == "PE"]

    # tunnel_type: ~30 SRV6_TE, ~20 SRV6_BE, ~20 MPLS_LDP, ~10 MPLS_TE
    tunnel_types = ["SRV6_TE"] * 30 + ["SRV6_BE"] * 20 + ["MPLS_LDP"] * 20 + ["MPLS_TE"] * 10
    random.shuffle(tunnel_types)

    # CRITICAL Q08: Some tunnels carrying GOLD VPNs
    gold_vpn_ids = [v["vpn_id"] for v in vpn_list if v["service_level"] == "GOLD"]
    all_vpn_ids = [v["vpn_id"] for v in vpn_list]

    # Build policy lookup for SRV6_TE tunnels
    available_policies = list(policy_list)

    for i in range(80):
        tun_seq = i + 1
        tunnel_id = str(uuid.uuid4())
        tunnel_type = tunnel_types[i]

        source_ne = random.choice(pe_nes)
        dest_candidates = [ne for ne in pe_nes if ne["ne_id"] != source_ne["ne_id"]]
        dest_ne = random.choice(dest_candidates) if dest_candidates else source_ne

        # Associate VPN IDs
        if i < 10 and gold_vpn_ids:
            # First 10 tunnels carry GOLD VPNs (for Q08)
            chosen_vpns = random.sample(gold_vpn_ids, min(random.randint(1, 3), len(gold_vpn_ids)))
        elif random.random() < 0.6:
            chosen_vpns = random.sample(all_vpn_ids, min(random.randint(1, 4), len(all_vpn_ids)))
        else:
            chosen_vpns = []

        associated_vpn_ids = json.dumps(chosen_vpns) if chosen_vpns else None

        # Policy reference for SRV6_TE tunnels
        policy_id = None
        if tunnel_type == "SRV6_TE" and available_policies:
            pol = random.choice(available_policies)
            policy_id = pol["policy_id"]

        bandwidth = random.choice([1000, 10000, 50000, 100000])
        measured_latency = round(random.uniform(5, 30), 3)
        measured_jitter = round(random.uniform(0.5, 5), 3)

        rows.append((
            tunnel_id,
            f"{tunnel_type}-{source_ne['city_code']}-{dest_ne['city_code']}-{tun_seq:03d}",
            tunnel_type,
            source_ne["ne_id"],
            f"2001:DB8:{source_ne['ne_idx']+1:X}::1" if "SRV6" in tunnel_type else source_ne.get("ne_id"),
            dest_ne["ne_id"],
            f"2001:DB8:{dest_ne['ne_idx']+1:X}::1" if "SRV6" in tunnel_type else dest_ne.get("ne_id"),
            policy_id,
            str(uuid.uuid4()),
            bandwidth,
            measured_latency,
            measured_jitter,
            random.randint(2, 6),
            random.choice(["NONE", "HOT_STANDBY", "TI_LFA", "FRR"]),
            random.random() < 0.7,
            associated_vpn_ids,
            f"TG-{(i//5)+1:03d}" if random.random() < 0.3 else None,
            random.choice(["ANY_TO_ANY", "HUB_SPOKE", None]),
            random.choice(["BGP_SR_POLICY", "PCEP", "RSVP_TE", "STATIC"]),
            "UP", "UP" if random.random() < 0.93 else "DOWN",
            random.randint(0, 7),
            random.randint(0, 7),
            f"隧道描述-{tunnel_id}",
            _ts(NOW - timedelta(days=random.randint(30, 365))),
            _ts(NOW - timedelta(hours=random.randint(1, 48))),
        ))

        tunnel_list.append({
            "tunnel_id": tunnel_id,
            "tunnel_type": tunnel_type,
            "source_ne_id": source_ne["ne_id"],
            "dest_ne_id": dest_ne["ne_id"],
            "associated_vpn_ids": chosen_vpns,
        })

    return rows, tunnel_list


# ---------------------------------------------------------------------------
# t_ne_perf_kpi  (~67200 rows)
# ---------------------------------------------------------------------------

def _generate_ne_perf_kpi(ne_list):
    """50 NEs x 1344 time points = 67200 rows."""
    n_nes = len(ne_list)
    n_points = 1344  # 14 days, 15-min granularity

    # Time points: past 14 days
    start_time = NOW - timedelta(days=14)
    times = [start_time + timedelta(minutes=15 * t) for t in range(n_points)]

    rows = []
    kpi_id = 0

    # CRITICAL Q07: At least 3 NEs with cpu_usage_avg > 80 in recent 24h
    # Pick NE indices 0, 1, 2 as high-CPU NEs
    high_cpu_nes = set(range(3))

    for ne_idx_local in range(n_nes):
        ne = ne_list[ne_idx_local]
        ne_id = ne["ne_id"]

        # Generate arrays with numpy for efficiency
        if ne_idx_local in high_cpu_nes:
            # High CPU in last 24h (last 96 points)
            cpu_avg = np.concatenate([
                np.random.uniform(30, 60, n_points - 96),
                np.random.uniform(82, 98, 96),
            ])
        else:
            # Normal - no random anomalies to keep Q07 count tight
            cpu_avg = np.random.uniform(20, 60, n_points)

        cpu_max = cpu_avg + np.random.uniform(2, 15, n_points)
        cpu_max = np.clip(cpu_max, 0, 100)

        mem_avg = np.random.uniform(40, 75, n_points)
        mem_max = mem_avg + np.random.uniform(2, 10, n_points)
        mem_max = np.clip(mem_max, 0, 100)

        temp_avg = np.random.uniform(35, 55, n_points)
        temp_max = temp_avg + np.random.uniform(1, 8, n_points)

        power_w = np.random.uniform(800, 2000, n_points)
        fan_rpm = np.random.randint(5000, 9000, n_points)
        uptime_s = np.arange(n_points) * 900 + random.randint(100000, 30000000)

        fib_usage = np.random.randint(100000, 500000, n_points)
        fib_cap = np.full(n_points, 2000000)
        arp_count = np.random.randint(1000, 10000, n_points)
        route_v4 = np.random.randint(500000, 900000, n_points)
        route_v6 = np.random.randint(50000, 200000, n_points)

        bgp_total = random.randint(15, 30)
        bgp_up = np.random.randint(max(bgp_total - 3, 10), bgp_total + 1, n_points)
        isis_adj = np.random.randint(2, 6, n_points)

        alarm_crit = np.random.choice([0, 0, 0, 0, 0, 1, 2], n_points)
        alarm_major = np.random.choice([0, 0, 0, 1, 1, 2], n_points)
        alarm_minor = np.random.choice([0, 0, 1, 2, 3], n_points)

        for t_idx in range(n_points):
            kpi_id += 1
            rows.append((
                kpi_id, ne_id,
                _ts(times[t_idx]),
                15,
                round(float(cpu_avg[t_idx]), 2),
                round(float(cpu_max[t_idx]), 2),
                round(float(mem_avg[t_idx]), 2),
                round(float(mem_max[t_idx]), 2),
                round(float(temp_avg[t_idx]), 2),
                round(float(temp_max[t_idx]), 2),
                round(float(power_w[t_idx]), 2),
                int(fan_rpm[t_idx]),
                int(uptime_s[t_idx]),
                int(fib_usage[t_idx]),
                int(fib_cap[t_idx]),
                int(arp_count[t_idx]),
                int(route_v4[t_idx]),
                int(route_v6[t_idx]),
                int(bgp_up[t_idx]),
                bgp_total,
                int(isis_adj[t_idx]),
                int(alarm_crit[t_idx]),
                int(alarm_major[t_idx]),
                int(alarm_minor[t_idx]),
                _ts(times[t_idx] + timedelta(seconds=30)),
            ))

    return rows


# ---------------------------------------------------------------------------
# t_interface_perf_kpi  (~5000 rows)
# ---------------------------------------------------------------------------

def _generate_interface_perf_kpi(if_list, ne_list):
    """Sample 30% of PHYSICAL interfaces x ~55 time points (from 14-day window)."""
    phy_ifs = [iface for iface in if_list if iface["if_type"] == "PHYSICAL"]
    sampled = random.sample(phy_ifs, max(1, int(len(phy_ifs) * 0.30)))

    ne_lookup = {ne["ne_id"]: ne for ne in ne_list}

    n_points = 55
    start_time = NOW - timedelta(days=14)
    # Pick 55 evenly spaced points from 1344
    step = 1344 // n_points
    time_indices = list(range(0, 1344, step))[:n_points]
    times = [start_time + timedelta(minutes=15 * t) for t in time_indices]

    rows = []
    kpi_id = 0

    for iface in sampled:
        if_id = iface["if_id"]
        ne_id = iface["ne_id"]
        speed = iface["speed_mbps"] or 10000

        # CRITICAL Q09: Vary out_bandwidth_usage_pct mix of <30, 30-70, 70-90, >90
        # Random base profile per interface
        profile = random.random()
        if profile < 0.3:
            bw_base = np.random.uniform(5, 28, n_points)
        elif profile < 0.6:
            bw_base = np.random.uniform(30, 68, n_points)
        elif profile < 0.85:
            bw_base = np.random.uniform(70, 88, n_points)
        else:
            bw_base = np.random.uniform(85, 99, n_points)

        # Add some anomalies
        anomaly_mask = np.random.random(n_points) < 0.05
        bw_base[anomaly_mask] = np.random.uniform(85, 99, anomaly_mask.sum())

        in_bw_pct = bw_base * np.random.uniform(0.7, 1.0, n_points)
        out_bw_pct = bw_base

        # Derive octets from bandwidth usage
        period_seconds = 900  # 15 min
        speed_bps = speed * 1_000_000
        in_octets = (in_bw_pct / 100.0 * speed_bps * period_seconds / 8).astype(np.int64)
        out_octets = (out_bw_pct / 100.0 * speed_bps * period_seconds / 8).astype(np.int64)

        in_packets = (in_octets / random.randint(500, 1500)).astype(np.int64)
        out_packets = (out_octets / random.randint(500, 1500)).astype(np.int64)

        for t_idx in range(n_points):
            kpi_id += 1
            in_uni = int(in_packets[t_idx] * 0.95)
            out_uni = int(out_packets[t_idx] * 0.95)
            in_multi = int(in_packets[t_idx] * 0.03)
            out_multi = int(out_packets[t_idx] * 0.03)
            in_broad = int(in_packets[t_idx] * 0.02)
            out_broad = int(out_packets[t_idx] * 0.02)

            in_peak = round(float(in_bw_pct[t_idx]) / 100.0 * speed * random.uniform(1.0, 1.3), 2)
            out_peak = round(float(out_bw_pct[t_idx]) / 100.0 * speed * random.uniform(1.0, 1.3), 2)

            in_err = random.randint(0, 5) if random.random() < 0.05 else 0
            out_err = random.randint(0, 3) if random.random() < 0.03 else 0
            in_disc = random.randint(0, 100) if random.random() < 0.05 else 0
            out_disc = random.randint(0, 50) if random.random() < 0.03 else 0
            crc_err = random.randint(0, 10) if random.random() < 0.02 else 0

            oper_status = iface["oper_status"]

            rows.append((
                kpi_id, if_id, ne_id,
                _ts(times[t_idx]),
                15,
                int(in_octets[t_idx]), int(out_octets[t_idx]),
                int(in_packets[t_idx]), int(out_packets[t_idx]),
                in_uni, out_uni,
                in_multi, out_multi,
                in_broad, out_broad,
                round(float(in_bw_pct[t_idx]), 2),
                round(float(out_bw_pct[t_idx]), 2),
                in_peak, out_peak,
                in_err, out_err,
                in_disc, out_disc,
                crc_err,
                0,  # collision_count
                oper_status,
                random.randint(0, 2) if random.random() < 0.1 else 0,
                _ts(times[t_idx] + timedelta(seconds=30)),
            ))

    return rows


# ---------------------------------------------------------------------------
# t_tunnel_perf_kpi  (~3000 rows)
# ---------------------------------------------------------------------------

def _generate_tunnel_perf_kpi(tunnel_list, vpn_list):
    """Sample 50% of tunnels x ~75 time points (from 14-day window)."""
    sampled = random.sample(tunnel_list, max(1, int(len(tunnel_list) * 0.5)))

    n_points = 75
    start_time = NOW - timedelta(days=14)
    step = 1344 // n_points
    time_indices = list(range(0, 1344, step))[:n_points]
    times = [start_time + timedelta(minutes=15 * t) for t in time_indices]

    # Build VPN lookup for max_latency
    vpn_lookup = {v["vpn_id"]: v for v in vpn_list}

    rows = []
    kpi_id = 0

    for tunnel in sampled:
        tunnel_id = tunnel["tunnel_id"]
        source_ne_id = tunnel["source_ne_id"]
        dest_ne_id = tunnel["dest_ne_id"]
        assoc_vpns = tunnel["associated_vpn_ids"]

        # Check if carrying GOLD VPN
        carries_gold = False
        gold_max_latency = None
        for vid in assoc_vpns:
            v = vpn_lookup.get(vid)
            if v and v["service_level"] == "GOLD":
                carries_gold = True
                gold_max_latency = v["max_latency_ms"]
                break

        for t_idx in range(n_points):
            kpi_id += 1

            # CRITICAL Q08: Some tunnels carrying GOLD VPNs with latency > max_latency_ms
            if carries_gold and random.random() < 0.15:
                # SLA violation
                latency_avg = round(random.uniform(25, 60), 3)
            elif random.random() < 0.10:
                # General anomaly
                latency_avg = round(random.uniform(50, 120), 3)
            else:
                latency_avg = round(random.uniform(5, 18), 3)

            latency_max = round(latency_avg + random.uniform(2, 15), 3)
            latency_min = round(max(1, latency_avg - random.uniform(2, 8)), 3)

            jitter_avg = round(random.uniform(0.5, 5), 3)
            jitter_max = round(jitter_avg + random.uniform(1, 5), 3)
            loss_pct = round(random.uniform(0, 0.05), 4) if random.random() < 0.9 else round(random.uniform(0.1, 2), 4)

            bw_usage = round(random.uniform(20, 80), 2)
            fwd_octets = random.randint(1_000_000_000, 100_000_000_000)
            fwd_packets = fwd_octets // random.randint(500, 1500)
            rtt_avg = round(latency_avg * 2 + random.uniform(-2, 2), 3)
            rtt_max = round(latency_max * 2 + random.uniform(0, 5), 3)

            # SLA violation detection
            sla_violation = False
            sla_violation_type = None
            if gold_max_latency and latency_avg > gold_max_latency:
                sla_violation = True
                sla_violation_type = "LATENCY"
            elif latency_avg > 50:
                sla_violation = True
                sla_violation_type = "LATENCY"
            if loss_pct > 0.1:
                sla_violation = True
                sla_violation_type = (sla_violation_type + ",LOSS") if sla_violation_type else "LOSS"

            oper_status = "UP" if random.random() < 0.95 else "DOWN"

            rows.append((
                kpi_id, tunnel_id, source_ne_id, dest_ne_id,
                _ts(times[t_idx]),
                15,
                latency_avg, latency_max, latency_min,
                jitter_avg, jitter_max,
                loss_pct,
                fwd_octets, fwd_packets,
                bw_usage,
                rtt_avg, rtt_max,
                random.randint(0, 1) if random.random() < 0.1 else 0,
                oper_status,
                sla_violation,
                sla_violation_type,
                _ts(times[t_idx] + timedelta(seconds=30)),
            ))

    return rows


# ---------------------------------------------------------------------------
# t_vpn_sla_kpi  (~2000 rows)
# ---------------------------------------------------------------------------

def _generate_vpn_sla_kpi(vpn_list, ne_list):
    """All 30 VPNs x ~67 time points (from 14-day window)."""
    pe_nes = [ne for ne in ne_list if ne["role"] == "PE"]
    n_points = 67
    start_time = NOW - timedelta(days=14)
    step = 1344 // n_points
    time_indices = list(range(0, 1344, step))[:n_points]
    times = [start_time + timedelta(minutes=15 * t) for t in time_indices]

    rows = []
    kpi_id = 0

    # CRITICAL Q15: Mark first 2 GOLD VPNs as "troubled" with heavy SLA violations
    gold_vpns = [v for v in vpn_list if v["service_level"] == "GOLD"]
    troubled_vpn_ids = {v["vpn_id"] for v in gold_vpns[:2]} if len(gold_vpns) >= 2 else set()

    for vpn in vpn_list:
        vpn_id = vpn["vpn_id"]
        level = vpn["service_level"]
        is_gold = level == "GOLD"
        is_active = vpn["admin_status"] == "ACTIVE"
        max_lat = vpn["max_latency_ms"]
        is_troubled = vpn_id in troubled_vpn_ids

        # Pick random PE pair for measurement
        pe1 = random.choice(pe_nes)
        pe2_candidates = [ne for ne in pe_nes if ne["ne_id"] != pe1["ne_id"]]
        pe2 = random.choice(pe2_candidates) if pe2_candidates else pe1

        for t_idx in range(n_points):
            kpi_id += 1

            # Troubled GOLD VPNs have much worse metrics
            if is_troubled:
                e2e_lat_avg = round(random.uniform(15, 60), 3)
                e2e_jit_avg = round(random.uniform(3, 15), 3)
                e2e_loss = round(random.uniform(0.01, 0.5), 4)
                avail = round(random.uniform(96, 99.5), 3)
            else:
                # Normal latency
                if random.random() < 0.10:
                    e2e_lat_avg = round(random.uniform(25, 80), 3)
                else:
                    e2e_lat_avg = round(random.uniform(5, 20), 3)
                e2e_jit_avg = round(random.uniform(0.5, 5), 3)
                e2e_loss = round(random.uniform(0, 0.02), 4) if random.random() < 0.9 else round(random.uniform(0.05, 1), 4)
                if random.random() < 0.05:
                    avail = round(random.uniform(95, 98.5), 3)
                else:
                    avail = round(random.uniform(99.5, 99.99), 3)

            e2e_lat_max = round(e2e_lat_avg + random.uniform(2, 15), 3)
            e2e_jit_max = round(e2e_jit_avg + random.uniform(1, 5), 3)

            throughput = round(random.uniform(50, 5000), 2)
            route_count = random.randint(100, 5000)
            route_flap = random.randint(0, 2) if random.random() < 0.1 else 0

            # SLA met flags
            sla_lat_met = e2e_lat_avg <= max_lat
            sla_jit_met = e2e_jit_avg <= 10
            sla_loss_met = e2e_loss <= 0.1
            sla_avail_met = avail >= 99.5

            # CRITICAL Q15: Additional random failures for GOLD VPNs
            if is_gold and not is_troubled and random.random() < 0.15:
                choice = random.randint(0, 3)
                if choice == 0:
                    sla_lat_met = False
                elif choice == 1:
                    sla_jit_met = False
                elif choice == 2:
                    sla_loss_met = False
                else:
                    sla_avail_met = False

            sla_overall = sla_lat_met and sla_jit_met and sla_loss_met and sla_avail_met

            # CRITICAL Q11: Some ACTIVE VPNs with sla_overall_met=FALSE
            if is_active and random.random() < 0.08:
                sla_overall = False

            mos = round(random.uniform(3.5, 4.8), 2) if sla_overall else round(random.uniform(2.5, 3.5), 2)
            qos_class = random.choice(["EF", "AF41", "AF31", "BE"])

            rows.append((
                kpi_id, vpn_id,
                pe1["ne_id"], pe2["ne_id"],
                _ts(times[t_idx]),
                15,
                e2e_lat_avg, e2e_lat_max,
                e2e_jit_avg, e2e_jit_max,
                e2e_loss,
                avail,
                throughput,
                route_count,
                route_flap,
                sla_lat_met, sla_jit_met, sla_loss_met, sla_avail_met,
                sla_overall,
                mos,
                qos_class,
                _ts(times[t_idx] + timedelta(seconds=30)),
            ))

    return rows


# ===========================================================================
# SQL insert helpers
# ===========================================================================

_INSERT_SQL = {
    "t_site": """INSERT INTO t_site (
        site_id, site_name, site_code, site_type, region, province, city,
        address, longitude, latitude, tier, total_rack_count, used_rack_count,
        power_capacity_kw, cooling_type, operator, contact_person, contact_phone,
        commissioning_date, contract_expire_date, status, description
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",

    "t_network_element": """INSERT INTO t_network_element (
        ne_id, ne_name, ne_type, vendor, model, software_version, patch_version,
        role, management_ip, loopback_ipv4, loopback_ipv6, router_id,
        as_number, isis_system_id, isis_area_id, srv6_locator,
        mpls_enabled, srv6_enabled, netconf_enabled, telemetry_enabled,
        site_id, rack_position, serial_number, asset_id,
        commissioning_date, maintenance_expire,
        admin_status, oper_status, description, created_at, updated_at
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",

    "t_board": """INSERT INTO t_board (
        board_id, ne_id, slot_number, board_type, board_name,
        hardware_version, firmware_version, serial_number,
        port_count, port_type, forwarding_capacity_gbps, memory_total_mb,
        temperature_threshold, power_consumption_w,
        admin_status, oper_status, install_date, last_reboot_time,
        uptime_hours, description, created_at, updated_at
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",

    "t_interface": """INSERT INTO t_interface (
        if_id, ne_id, board_id, if_name, if_index, if_type, phy_type,
        speed_mbps, mtu, ipv4_address, ipv4_mask, ipv6_address, ipv6_prefix_len,
        mac_address, vlan_id, vrf_name, trunk_id, trunk_member_count,
        isis_enabled, isis_cost, ospf_enabled, bfd_enabled, qos_profile,
        admin_status, oper_status, last_change_time, description,
        created_at, updated_at
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",

    "t_physical_link": """INSERT INTO t_physical_link (
        link_id, link_name, link_type, a_ne_id, a_if_id, a_site_id,
        z_ne_id, z_if_id, z_site_id, bandwidth_mbps, distance_km, latency_ms,
        fiber_core_count, wavelength_nm, cable_id, is_intra_site,
        protection_type, carrier, circuit_id, sla_class,
        admin_status, oper_status, commissioning_date, contract_expire_date,
        monthly_cost, description, created_at, updated_at
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",

    "t_vrf_instance": """INSERT INTO t_vrf_instance (
        vrf_id, ne_id, vrf_name, route_distinguisher,
        vpn_target_import, vpn_target_export, address_family, label_mode,
        tunnel_policy, srv6_locator, srv6_sid_end_dt4, srv6_sid_end_dt6,
        evpn_type, max_routes, current_route_count, associated_if_count,
        customer_id, customer_name, service_type,
        admin_status, oper_status, description, created_at, updated_at
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",

    "t_l3vpn_service": """INSERT INTO t_l3vpn_service (
        vpn_id, vpn_name, vpn_type, topology, customer_id, customer_name,
        service_level, bandwidth_mbps, max_latency_ms, max_jitter_ms,
        max_packet_loss_pct, pe_count, site_count, underlay_type,
        encryption_enabled, multicast_enabled, route_distinguisher, vpn_target,
        contract_start_date, contract_end_date, monthly_fee,
        admin_status, oper_status, deploy_status, last_audit_time,
        description, created_at, updated_at
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",

    "t_vpn_pe_binding": """INSERT INTO t_vpn_pe_binding (
        binding_id, vpn_id, ne_id, vrf_id, if_id, pe_role,
        ce_ipv4, pe_ipv4, ce_ipv6, pe_ipv6, ce_as_number,
        routing_protocol, access_bandwidth_mbps, vlan_id, encapsulation,
        site_name, admin_status, oper_status, description,
        created_at, updated_at
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",

    "t_srv6_policy": """INSERT INTO t_srv6_policy (
        policy_id, policy_name, source_ne_id, endpoint_ipv6, dest_ne_id,
        color, distinguisher, binding_sid, preference,
        segment_list_count, segment_list, explicit_path,
        provision_type, sla_type, max_latency_ms, max_jitter_ms,
        min_bandwidth_mbps, hop_count, associated_vpn_count, ecmp_count,
        admin_status, oper_status, deploy_source, last_path_change,
        description, created_at, updated_at
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",

    "t_tunnel": """INSERT INTO t_tunnel (
        tunnel_id, tunnel_name, tunnel_type, source_ne_id, source_ip,
        dest_ne_id, dest_ip, policy_id, tunnel_if_id, bandwidth_mbps,
        measured_latency_ms, measured_jitter_ms, path_hop_count,
        protection_type, is_bidirectional, associated_vpn_ids,
        tunnel_group_id, group_type, signaling_protocol,
        admin_status, oper_status, setup_priority, hold_priority,
        description, created_at, updated_at
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",

    "t_ne_perf_kpi": """INSERT INTO t_ne_perf_kpi (
        kpi_id, ne_id, collect_time, granularity_min,
        cpu_usage_avg_pct, cpu_usage_max_pct,
        memory_usage_avg_pct, memory_usage_max_pct,
        temperature_avg_c, temperature_max_c,
        power_consumption_w, fan_speed_rpm, uptime_seconds,
        fib_usage_count, fib_capacity, arp_entry_count,
        route_count_ipv4, route_count_ipv6,
        bgp_peer_up_count, bgp_peer_total_count, isis_adj_up_count,
        alarm_critical_count, alarm_major_count, alarm_minor_count,
        created_at
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",

    "t_interface_perf_kpi": """INSERT INTO t_interface_perf_kpi (
        kpi_id, if_id, ne_id, collect_time, granularity_min,
        in_octets, out_octets, in_packets, out_packets,
        in_unicast_packets, out_unicast_packets,
        in_multicast_packets, out_multicast_packets,
        in_broadcast_packets, out_broadcast_packets,
        in_bandwidth_usage_pct, out_bandwidth_usage_pct,
        in_peak_rate_mbps, out_peak_rate_mbps,
        in_error_packets, out_error_packets,
        in_discard_packets, out_discard_packets,
        crc_error_count, collision_count,
        oper_status, status_change_count, created_at
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",

    "t_tunnel_perf_kpi": """INSERT INTO t_tunnel_perf_kpi (
        kpi_id, tunnel_id, source_ne_id, dest_ne_id,
        collect_time, granularity_min,
        latency_avg_ms, latency_max_ms, latency_min_ms,
        jitter_avg_ms, jitter_max_ms, packet_loss_rate_pct,
        forward_octets, forward_packets, bandwidth_usage_pct,
        rtt_avg_ms, rtt_max_ms, path_change_count,
        oper_status, sla_violation, sla_violation_type, created_at
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",

    "t_vpn_sla_kpi": """INSERT INTO t_vpn_sla_kpi (
        kpi_id, vpn_id, pe_ne_id, remote_pe_ne_id,
        collect_time, granularity_min,
        e2e_latency_avg_ms, e2e_latency_max_ms,
        e2e_jitter_avg_ms, e2e_jitter_max_ms,
        e2e_packet_loss_pct, availability_pct, throughput_mbps,
        vpn_route_count, route_flap_count,
        sla_latency_met, sla_jitter_met, sla_loss_met, sla_availability_met,
        sla_overall_met, mos_score, qos_class_applied, created_at
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
}


# ===========================================================================
# Anomaly injection — ensures edge-case test queries return non-zero rows
# ===========================================================================

def _inject_anomalies(con):
    """Inject edge-case data to ensure all 100 test cases return non-zero rows."""

    # Q18: admin_status=DOWN but oper_status=UP (2 devices)
    con.execute("""
        UPDATE t_network_element SET admin_status='DOWN'
        WHERE ne_id IN (SELECT ne_id FROM t_network_element WHERE oper_status='UP' LIMIT 2)
    """)

    # Q24: P devices with mpls_enabled=FALSE (2 devices)
    con.execute("""
        UPDATE t_network_element SET mpls_enabled=FALSE
        WHERE ne_id IN (SELECT ne_id FROM t_network_element WHERE role='P' LIMIT 2)
    """)

    # Q31: Has srv6_locator but srv6_enabled=FALSE (2 devices)
    con.execute("""
        UPDATE t_network_element SET srv6_enabled=FALSE
        WHERE ne_id IN (SELECT ne_id FROM t_network_element WHERE srv6_locator IS NOT NULL AND srv6_enabled LIMIT 2)
    """)

    # Q16/Q47: Sites with contract expiring within 90 days
    # 使用固定偏移而不是 DATE '2025-03-29'（因为 refresh_timestamps 会平移日期）
    con.execute(f"""
        UPDATE t_site SET contract_expire_date = DATE '{NOW.strftime("%Y-%m-%d")}' + INTERVAL 30 DAY
        WHERE site_id IN (SELECT site_id FROM t_site WHERE status='ACTIVE' LIMIT 3)
    """)

    # Q34: VPN with contract already expired but still ACTIVE
    con.execute(f"""
        UPDATE t_l3vpn_service SET contract_end_date = DATE '{NOW.strftime("%Y-%m-%d")}' - INTERVAL 30 DAY
        WHERE vpn_id IN (SELECT vpn_id FROM t_l3vpn_service WHERE admin_status='ACTIVE' LIMIT 2)
    """)

    # Q37: Explicit path SRv6 Policy with LOW_LATENCY and max_latency < 10ms
    con.execute("""
        UPDATE t_srv6_policy SET explicit_path=TRUE, sla_type='LOW_LATENCY', max_latency_ms=5.0
        WHERE policy_id IN (SELECT policy_id FROM t_srv6_policy LIMIT 2)
    """)

    # Q40: Interface oper=UP but latest KPI sample shows oper=DOWN
    con.execute("""
        UPDATE t_interface_perf_kpi SET oper_status='DOWN'
        WHERE kpi_id IN (
            SELECT k.kpi_id FROM t_interface_perf_kpi k
            JOIN t_interface i ON k.if_id = i.if_id
            WHERE i.oper_status='UP'
            ORDER BY k.collect_time DESC LIMIT 5
        )
    """)

    # Q50: VRF route utilization > 80%
    con.execute("""
        UPDATE t_vrf_instance SET current_route_count = max_routes - 1
        WHERE vrf_id IN (SELECT vrf_id FROM t_vrf_instance WHERE max_routes > 0 LIMIT 3)
    """)

    # Q55: Same customer with both SRV6_TE and MPLS_TE
    con.execute("""
        UPDATE t_l3vpn_service SET underlay_type='MPLS_TE'
        WHERE vpn_id IN (
            SELECT vpn_id FROM t_l3vpn_service
            WHERE customer_id IN (SELECT customer_id FROM t_l3vpn_service WHERE underlay_type='SRV6_TE' LIMIT 1)
            AND underlay_type != 'SRV6_TE'
            LIMIT 1
        )
    """)

    # Q59: VRF with tunnel_policy but no RT import/export
    con.execute("""
        UPDATE t_vrf_instance SET vpn_target_import=NULL, vpn_target_export=NULL
        WHERE vrf_id IN (SELECT vrf_id FROM t_vrf_instance WHERE tunnel_policy IS NOT NULL AND tunnel_policy != '' LIMIT 2)
    """)

    # Q76: Devices with no board records — 插入没有板卡的新设备（避免外键级联问题）
    import uuid as _uuid
    for i in range(2):
        nid = str(_uuid.uuid4())
        con.execute(f"""
            INSERT INTO t_network_element (ne_id, ne_name, ne_type, vendor, model, role,
                management_ip, admin_status, oper_status, created_at, updated_at)
            VALUES ('{nid}', 'NOBOARD-TEST-{i+1}', 'ROUTER', 'HUAWEI', 'NE40E-X16A', 'CE',
                '10.99.99.{i+1}', 'UP', 'UP', TIMESTAMP '2025-03-29 12:00:00', TIMESTAMP '2025-03-29 12:00:00')
        """)

    # Q83: VPN binding with VRF that has current_route_count=0
    con.execute("""
        UPDATE t_vrf_instance SET current_route_count=0
        WHERE vrf_id IN (
            SELECT v.vrf_id FROM t_vrf_instance v
            JOIN t_vpn_pe_binding b ON v.vrf_id = b.vrf_id
            LIMIT 3
        )
    """)

    # Q42: BGP peer availability < 80%
    con.execute("""
        UPDATE t_ne_perf_kpi SET bgp_peer_up_count = 1, bgp_peer_total_count = 5
        WHERE kpi_id IN (
            SELECT kpi_id FROM t_ne_perf_kpi
            WHERE ne_id IN (SELECT ne_id FROM t_network_element LIMIT 2)
            ORDER BY collect_time DESC LIMIT 200
        )
    """)

    # Q46: Temperature exceeding board threshold
    con.execute("""
        UPDATE t_ne_perf_kpi SET temperature_avg_c = 85.0, temperature_max_c = 92.0
        WHERE kpi_id IN (
            SELECT kpi_id FROM t_ne_perf_kpi
            WHERE ne_id IN (SELECT ne_id FROM t_board WHERE temperature_threshold IS NOT NULL LIMIT 1)
            ORDER BY collect_time DESC LIMIT 50
        )
    """)

    # Q92: High CPU (>80%) AND high interface errors (>1000) for same device
    con.execute("""
        UPDATE t_interface_perf_kpi SET in_error_packets = 500, out_error_packets = 600
        WHERE kpi_id IN (
            SELECT k.kpi_id FROM t_interface_perf_kpi k
            WHERE k.ne_id IN (SELECT ne_id FROM t_network_element LIMIT 2)
            ORDER BY k.collect_time DESC LIMIT 200
        )
    """)

    # Q98: Tunnels with path changes AND high jitter
    con.execute("""
        UPDATE t_tunnel_perf_kpi SET path_change_count = 3, jitter_avg_ms = 15.0
        WHERE kpi_id IN (
            SELECT kpi_id FROM t_tunnel_perf_kpi ORDER BY collect_time DESC LIMIT 20
        )
    """)

    # Q94: Tunnel latency exceeding policy constraint
    con.execute("""
        UPDATE t_tunnel_perf_kpi SET latency_avg_ms = 100.0
        WHERE kpi_id IN (
            SELECT k.kpi_id FROM t_tunnel_perf_kpi k
            JOIN t_tunnel t ON k.tunnel_id = t.tunnel_id
            WHERE t.policy_id IS NOT NULL
            ORDER BY k.collect_time DESC LIMIT 30
        )
    """)

    # ── 精确修复（hotfix 验证后固化）──

    # Q14: 对比上周/本周带宽增长>20% — 某站点上周低利用率+本周高利用率
    site_row = con.execute("""
        SELECT ne.site_id FROM t_interface_perf_kpi k
        JOIN t_network_element ne ON k.ne_id=ne.ne_id
        WHERE k.collect_time >= DATE '2025-03-29' - 14
        GROUP BY ne.site_id
        HAVING COUNT(DISTINCT CASE WHEN k.collect_time >= DATE '2025-03-29' - 7 THEN 1 END) > 0
        AND COUNT(DISTINCT CASE WHEN k.collect_time < DATE '2025-03-29' - 7 THEN 1 END) > 0
        LIMIT 1
    """).fetchone()
    if site_row:
        sid = site_row[0]
        con.execute(f"UPDATE t_interface_perf_kpi SET out_bandwidth_usage_pct=10.0 WHERE ne_id IN (SELECT ne_id FROM t_network_element WHERE site_id='{sid}') AND collect_time < DATE '2025-03-29' - 7")
        con.execute(f"UPDATE t_interface_perf_kpi SET out_bandwidth_usage_pct=60.0 WHERE ne_id IN (SELECT ne_id FROM t_network_element WHERE site_id='{sid}') AND collect_time >= DATE '2025-03-29' - 7")

    # Q46: 降低板卡温度阈值使实际温度超标
    con.execute("UPDATE t_board SET temperature_threshold=40.0 WHERE board_id IN (SELECT board_id FROM t_board WHERE temperature_threshold IS NOT NULL LIMIT 3)")

    # Q47: VPN 合同 15 天后到期（30天内）
    con.execute("UPDATE t_l3vpn_service SET contract_end_date = DATE '2025-03-29' + INTERVAL 15 DAY WHERE vpn_id IN (SELECT vpn_id FROM t_l3vpn_service ORDER BY monthly_fee DESC LIMIT 3)")

    # Q51: BFD 启用且状态翻转>3次
    con.execute("""
        UPDATE t_interface_perf_kpi SET status_change_count = 5
        WHERE if_id IN (SELECT if_id FROM t_interface WHERE bfd_enabled LIMIT 3)
        AND collect_time >= TIMESTAMP '2025-03-29 12:00:00' - INTERVAL 24 HOUR
    """)

    # Q55: 同客户双承载（找有多条VPN的客户，一条设SRV6_TE另一条设MPLS_TE）
    multi_vpn_customer = con.execute("SELECT customer_id FROM t_l3vpn_service GROUP BY customer_id HAVING COUNT(*)>=2 LIMIT 1").fetchone()
    if multi_vpn_customer:
        cid = multi_vpn_customer[0]
        vpns = con.execute(f"SELECT vpn_id FROM t_l3vpn_service WHERE customer_id='{cid}' LIMIT 2").fetchall()
        if len(vpns) >= 2:
            con.execute(f"UPDATE t_l3vpn_service SET underlay_type='SRV6_TE' WHERE vpn_id='{vpns[0][0]}'")
            con.execute(f"UPDATE t_l3vpn_service SET underlay_type='MPLS_TE' WHERE vpn_id='{vpns[1][0]}'")

    # Q63: 设备综合健康分低于60 — CPU+内存+温度+告警全高
    con.execute("""
        UPDATE t_ne_perf_kpi SET cpu_usage_avg_pct=85, memory_usage_avg_pct=85,
            temperature_avg_c=70, alarm_critical_count=3, alarm_major_count=5
        WHERE ne_id IN (SELECT ne_id FROM t_network_element WHERE role='PE' LIMIT 1)
        AND collect_time >= TIMESTAMP '2025-03-29 12:00:00' - INTERVAL 7 DAY
    """)

    # Q70: SRv6 PE + LOW_LATENCY Policy + CPU>70
    pe_row = con.execute("SELECT ne_id FROM t_network_element WHERE srv6_enabled AND role='PE' LIMIT 1").fetchone()
    if pe_row:
        nid = pe_row[0]
        pol = con.execute(f"SELECT policy_id FROM t_srv6_policy WHERE source_ne_id='{nid}' LIMIT 1").fetchone()
        if pol:
            con.execute(f"UPDATE t_srv6_policy SET sla_type='LOW_LATENCY' WHERE policy_id='{pol[0]}'")
        con.execute(f"UPDATE t_ne_perf_kpi SET cpu_usage_avg_pct=75.0 WHERE ne_id='{nid}' AND collect_time >= TIMESTAMP '2025-03-29 12:00:00' - INTERVAL 7 DAY")

    # Q92: 高CPU + 高接口错误（同一设备）
    con.execute("""
        UPDATE t_interface_perf_kpi SET in_error_packets=600, out_error_packets=500
        WHERE ne_id IN (SELECT ne_id FROM t_ne_perf_kpi WHERE cpu_usage_avg_pct > 80 GROUP BY ne_id LIMIT 1)
        AND collect_time >= TIMESTAMP '2025-03-29 12:00:00' - INTERVAL 7 DAY
    """)

    # Q93: GOLD + SRV6_TE + 最新时延不达标
    gold_vpn = con.execute("SELECT vpn_id FROM t_l3vpn_service WHERE service_level='GOLD' AND underlay_type='SRV6_TE' LIMIT 1").fetchone()
    if not gold_vpn:
        gold_vpn = con.execute("SELECT vpn_id FROM t_l3vpn_service WHERE service_level='GOLD' LIMIT 1").fetchone()
        if gold_vpn:
            con.execute(f"UPDATE t_l3vpn_service SET underlay_type='SRV6_TE' WHERE vpn_id='{gold_vpn[0]}'")
    if gold_vpn:
        con.execute(f"""
            UPDATE t_vpn_sla_kpi SET sla_latency_met=FALSE, sla_overall_met=FALSE
            WHERE vpn_id='{gold_vpn[0]}'
            AND collect_time = (SELECT MAX(collect_time) FROM t_vpn_sla_kpi WHERE vpn_id='{gold_vpn[0]}')
        """)

    print("  异常数据注入完成")


# ===========================================================================
# Main entry point
# ===========================================================================

def populate_data(con):
    """向已建好表的 DuckDB 连接中插入 mock 数据。由 1_generate_data.py 调用。"""

    print("生成 OLTP 数据 ...")
    site_rows = _generate_sites()
    con.executemany(_INSERT_SQL["t_site"], site_rows)
    print(f"  t_site: {len(site_rows)} rows")

    ne_rows, ne_list = _generate_network_elements(site_rows)
    con.executemany(_INSERT_SQL["t_network_element"], ne_rows)
    print(f"  t_network_element: {len(ne_rows)} rows")

    board_rows, board_list = _generate_boards(ne_list)
    con.executemany(_INSERT_SQL["t_board"], board_rows)
    print(f"  t_board: {len(board_rows)} rows")

    if_rows, if_list = _generate_interfaces(ne_list, board_list)
    con.executemany(_INSERT_SQL["t_interface"], if_rows)
    print(f"  t_interface: {len(if_rows)} rows")

    vrf_rows, vrf_list = _generate_vrf_instances(ne_list)
    con.executemany(_INSERT_SQL["t_vrf_instance"], vrf_rows)
    print(f"  t_vrf_instance: {len(vrf_rows)} rows")

    vpn_rows, vpn_list = _generate_l3vpn_services()
    con.executemany(_INSERT_SQL["t_l3vpn_service"], vpn_rows)
    print(f"  t_l3vpn_service: {len(vpn_rows)} rows")

    link_rows, link_list = _generate_physical_links(ne_list, if_list)
    con.executemany(_INSERT_SQL["t_physical_link"], link_rows)
    print(f"  t_physical_link: {len(link_rows)} rows")

    binding_rows, binding_list = _generate_vpn_pe_bindings(vpn_list, ne_list, vrf_list, if_list)
    con.executemany(_INSERT_SQL["t_vpn_pe_binding"], binding_rows)
    print(f"  t_vpn_pe_binding: {len(binding_rows)} rows")

    policy_rows, policy_list = _generate_srv6_policies(ne_list)
    con.executemany(_INSERT_SQL["t_srv6_policy"], policy_rows)
    print(f"  t_srv6_policy: {len(policy_rows)} rows")

    tunnel_rows, tunnel_list = _generate_tunnels(ne_list, policy_list, vpn_list)
    con.executemany(_INSERT_SQL["t_tunnel"], tunnel_rows)
    print(f"  t_tunnel: {len(tunnel_rows)} rows")

    print("\n生成 KPI 数据 ...")
    ne_kpi_rows = _generate_ne_perf_kpi(ne_list)
    con.executemany(_INSERT_SQL["t_ne_perf_kpi"], ne_kpi_rows)
    print(f"  t_ne_perf_kpi: {len(ne_kpi_rows)} rows")

    if_kpi_rows = _generate_interface_perf_kpi(if_list, ne_list)
    con.executemany(_INSERT_SQL["t_interface_perf_kpi"], if_kpi_rows)
    print(f"  t_interface_perf_kpi: {len(if_kpi_rows)} rows")

    tun_kpi_rows = _generate_tunnel_perf_kpi(tunnel_list, vpn_list)
    con.executemany(_INSERT_SQL["t_tunnel_perf_kpi"], tun_kpi_rows)
    print(f"  t_tunnel_perf_kpi: {len(tun_kpi_rows)} rows")

    vpn_kpi_rows = _generate_vpn_sla_kpi(vpn_list, ne_list)
    con.executemany(_INSERT_SQL["t_vpn_sla_kpi"], vpn_kpi_rows)
    print(f"  t_vpn_sla_kpi: {len(vpn_kpi_rows)} rows")

    print("\n注入异常/边界数据 ...")
    _inject_anomalies(con)

    print("\n=== 汇总 ===")
    total = 0
    for tbl in [
        "t_site", "t_network_element", "t_board", "t_interface",
        "t_physical_link", "t_vrf_instance", "t_l3vpn_service",
        "t_vpn_pe_binding", "t_srv6_policy", "t_tunnel",
        "t_ne_perf_kpi", "t_interface_perf_kpi",
        "t_tunnel_perf_kpi", "t_vpn_sla_kpi",
    ]:
        count = con.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
        print(f"  {tbl:30s}  {count:>8,d} rows")
        total += count
    print(f"  {'TOTAL':30s}  {total:>8,d} rows")
