# 电信数据通信网管 Schema 扩展规范

> 目标：从当前 14 表 ~200 列扩展到 60-80 表 ~2000+ 列，覆盖数据通信网管的核心域。
> 参考：OpenConfig YANG、TMForum SID Resource Domain、RFC 4026/4664、IFIT/TWAMP 标准。

## 1. 当前 14 表回顾

```
存量域：t_site, t_network_element, t_board, t_interface, t_physical_link
VRF域：t_vrf_instance
业务域：t_l3vpn_service, t_vpn_pe_binding, t_srv6_policy, t_tunnel
性能域：t_ne_perf_kpi, t_interface_perf_kpi, t_tunnel_perf_kpi, t_vpn_sla_kpi
```

覆盖了基本骨架，但缺少：分域/子网管理、存量分表（扩展属性）、L2VPN、告警/工单、IFIT/TWAMP 性能采样、配置基线、IP 地址管理。

## 2. 业界数据模型参考

### 2.1 OpenConfig 模型分域

| 域 | OpenConfig 模型 | 覆盖实体 |
|----|----------------|---------|
| 平台 | platform | 设备硬件：机框/板卡/风扇/电源/光模块 |
| 接口 | interfaces | 物理口/子接口/LAG/Loopback，含计数器 |
| 网络实例 | network-instance | VRF/VPLS/EVPN 实例，路由表 |
| 路由 | bgp, ospf, isis | BGP 邻居/OSPF 区域/ISIS 级别 |
| MPLS | mpls, segment-routing | LSP/SR Policy/SID/BSID |
| QoS | qos | 队列/调度策略/流量整形 |
| ACL | acl | 访问控制列表/规则 |
| 遥测 | telemetry | 采样配置/订阅/传感器路径 |
| BFD | bfd | 双向转发检测会话 |

### 2.2 TMForum SID 资源域分层

```
管理域（Management Domain）
  └── 子网（Subnetwork）
        └── 网元（Managed Element）
              ├── 设备组件（Equipment / Board / Port）
              └── 逻辑资源（Logical Resource）
                    ├── 接口（Interface）
                    ├── 转发实例（Forwarding Instance / VRF）
                    └── 协议会话（Protocol Session）

拓扑连接（Topological Link）
  ├── 物理链路（Physical Link）
  ├── 逻辑链路（Logical Link / LAG）
  └── 路径（Trail / Connection / Tunnel）

业务资源（Service Resource）
  ├── L3VPN Service
  ├── L2VPN Service (VPWS / VPLS / EVPN)
  └── SLA Profile
```

### 2.3 IFIT / TWAMP 性能测量

**TWAMP（RFC 5357）— 双向主动测量**

| 指标 | 字段 | 说明 |
|------|------|------|
| 往返时延 | round_trip_delay_us | 微秒级 |
| 单向时延 | oneway_delay_us | 需要时钟同步 |
| 抖动 | jitter_us | 时延变化 |
| 丢包率 | packet_loss_pct | 发送/接收差值 |
| 会话标识 | session_id, sender_ip, reflector_ip | 关联到接口/隧道 |
| 采样间隔 | probe_interval_ms | 典型 100ms-1s |

**IFIT（In-situ Flow Information Telemetry）— 随流检测**

| 指标 | 字段 | 说明 |
|------|------|------|
| 逐跳时延 | hop_delay_us | 每个节点的转发时延 |
| 端到端时延 | e2e_delay_us | 全路径时延 |
| 丢包检测 | drop_count, drop_reason | 哪个节点丢的 |
| 流标识 | flow_id, src_ip, dst_ip, dscp | 五元组+DSCP |
| 路径信息 | path_nodes[] | 经过的节点列表 |
| 染色标记 | color_bit | 用于丢包统计 |

区别：TWAMP 是主动探测（发探针包），IFIT 是被动随流（在真实业务流里打标记）。生产环境通常两者都用——TWAMP 做基线测量，IFIT 做实时感知。

### 2.4 L2VPN 实体模型（RFC 4664）

```
L2VPN Service
  ├── 类型：VPWS（点到点）/ VPLS（多点）/ EVPN（以太网VPN）
  ├── Attachment Circuit (AC) — CE 到 PE 的接入电路
  ├── Pseudowire (PW) — PE 之间的伪线
  ├── VSI (Virtual Switching Instance) — VPLS 的虚拟交换实例
  └── 承载隧道 — MPLS LSP / SRv6 Policy
```

## 3. 扩展表设计

### 3.1 分域总览

从 14 表扩到 **8 个子域 ~65 表**：

| 子域 | 当前表数 | 扩展后 | 新增内容 |
|------|---------|--------|---------|
| 管理域 | 1 (t_site) | 4 | 分域/子网/站点扩展 |
| 设备域 | 3 (ne/board/interface) | 10 | 设备扩展属性/光模块/子接口/LAG/IP地址 |
| 拓扑域 | 1 (physical_link) | 4 | 逻辑链路/LAG链路/链路扩展 |
| 路由域 | 0 | 5 | BGP邻居/OSPF区域/ISIS/路由表/BFD |
| 业务域 | 4 (vpn/binding/srv6/tunnel) | 12 | L2VPN/EVPN/PW/AC/QoS/SLA模板 |
| 性能域 | 4 (kpi×4) | 12 | TWAMP/IFIT/接口计数器/流量统计 |
| 告警域 | 0 | 6 | 告警/告警历史/告警规则/事件 |
| 配置域 | 0 | 4 | 配置基线/变更记录/合规检查 |
| **合计** | **14** | **~57** | |

加上分表（`_ext`），总计约 **65-70 表，2000-2500 列**。

### 3.2 管理域（4 表）

#### t_management_domain — 管理域/分域
```sql
CREATE TABLE t_management_domain (
    domain_id        VARCHAR PRIMARY KEY,
    domain_name      VARCHAR NOT NULL,
    domain_type      VARCHAR NOT NULL,    -- 'backbone' / 'metro' / 'access'
    parent_domain_id VARCHAR,             -- 上级域（支持层级）
    region           VARCHAR NOT NULL,    -- 华北/华东/华南/西南/东北
    admin_contact    VARCHAR,
    description      VARCHAR,
    FOREIGN KEY (parent_domain_id) REFERENCES t_management_domain(domain_id)
);
```

#### t_subnet — 子网
```sql
CREATE TABLE t_subnet (
    subnet_id        VARCHAR PRIMARY KEY,
    subnet_name      VARCHAR NOT NULL,
    domain_id        VARCHAR NOT NULL,
    subnet_type      VARCHAR NOT NULL,    -- 'ip_backbone' / 'mpls_core' / 'access_ring'
    ip_prefix        VARCHAR,             -- '10.0.0.0/8'
    vlan_range       VARCHAR,             -- '100-200'
    ne_count         INTEGER DEFAULT 0,
    status           VARCHAR NOT NULL,    -- 'ACTIVE' / 'PLANNING' / 'DECOMMISSIONED'
    FOREIGN KEY (domain_id) REFERENCES t_management_domain(domain_id)
);
```

#### t_site（已有，增加外键）
```sql
ALTER TABLE t_site ADD COLUMN domain_id VARCHAR REFERENCES t_management_domain(domain_id);
ALTER TABLE t_site ADD COLUMN subnet_id VARCHAR REFERENCES t_subnet(subnet_id);
```

#### t_site_ext — 站点扩展属性
```sql
CREATE TABLE t_site_ext (
    site_id             VARCHAR PRIMARY KEY,
    building_name       VARCHAR,
    floor               INTEGER,
    room_name           VARCHAR,
    power_redundancy    VARCHAR,    -- 'N+1' / '2N'
    ups_capacity_kva    DECIMAL(10,2),
    fire_suppression    VARCHAR,    -- 'gas' / 'water' / 'none'
    physical_security   VARCHAR,    -- 'biometric' / 'card' / 'key'
    last_audit_date     DATE,
    FOREIGN KEY (site_id) REFERENCES t_site(site_id)
);
```

### 3.3 设备域（10 表）

#### t_network_element_ext — 网元扩展
```sql
CREATE TABLE t_network_element_ext (
    ne_id               VARCHAR PRIMARY KEY,
    chassis_type        VARCHAR,         -- '1U' / '2U' / 'modular'
    slot_count          INTEGER,
    max_power_watt      INTEGER,
    os_version          VARCHAR,         -- 'IOS-XR 7.9.1'
    patch_level         VARCHAR,
    boot_time           TIMESTAMP,
    uptime_hours        INTEGER,
    serial_number       VARCHAR,
    asset_tag           VARCHAR,
    contract_id         VARCHAR,
    eol_date            DATE,            -- End of Life
    eos_date            DATE,            -- End of Support
    last_config_backup  TIMESTAMP,
    config_compliance   VARCHAR,         -- 'COMPLIANT' / 'DRIFT' / 'UNKNOWN'
    FOREIGN KEY (ne_id) REFERENCES t_network_element(ne_id)
);
```

#### t_optical_module — 光模块
```sql
CREATE TABLE t_optical_module (
    module_id        VARCHAR PRIMARY KEY,
    if_id            VARCHAR NOT NULL,
    module_type      VARCHAR NOT NULL,    -- 'SFP' / 'SFP+' / 'QSFP28' / 'QSFP-DD'
    vendor           VARCHAR,
    wavelength_nm    INTEGER,             -- 1310 / 1550
    reach_km         INTEGER,             -- 传输距离
    tx_power_dbm     DECIMAL(6,2),
    rx_power_dbm     DECIMAL(6,2),
    temperature_c    DECIMAL(6,2),
    voltage_v        DECIMAL(6,3),
    serial_number    VARCHAR,
    dom_support      BOOLEAN DEFAULT TRUE,  -- Digital Optical Monitoring
    oper_status      VARCHAR NOT NULL,    -- 'UP' / 'DOWN' / 'DEGRADED'
    FOREIGN KEY (if_id) REFERENCES t_interface(if_id)
);
```

#### t_sub_interface — 子接口
```sql
CREATE TABLE t_sub_interface (
    sub_if_id        VARCHAR PRIMARY KEY,
    parent_if_id     VARCHAR NOT NULL,
    sub_if_index     INTEGER NOT NULL,    -- 子接口编号
    encapsulation    VARCHAR,             -- 'dot1q' / 'qinq'
    outer_vlan_id    INTEGER,
    inner_vlan_id    INTEGER,
    ip_address       VARCHAR,
    ip_mask          VARCHAR,
    mtu              INTEGER DEFAULT 1500,
    admin_status     VARCHAR NOT NULL,
    oper_status      VARCHAR NOT NULL,
    description      VARCHAR,
    FOREIGN KEY (parent_if_id) REFERENCES t_interface(if_id)
);
```

#### t_lag — 链路聚合组
```sql
CREATE TABLE t_lag (
    lag_id           VARCHAR PRIMARY KEY,
    ne_id            VARCHAR NOT NULL,
    lag_name         VARCHAR NOT NULL,     -- 'Eth-Trunk1'
    lag_mode         VARCHAR NOT NULL,     -- 'static' / 'lacp'
    member_count     INTEGER,
    min_active       INTEGER DEFAULT 1,
    max_bandwidth_mbps BIGINT,
    admin_status     VARCHAR NOT NULL,
    oper_status      VARCHAR NOT NULL,
    FOREIGN KEY (ne_id) REFERENCES t_network_element(ne_id)
);
```

#### t_lag_member — LAG 成员
```sql
CREATE TABLE t_lag_member (
    lag_id           VARCHAR NOT NULL,
    if_id            VARCHAR NOT NULL,
    member_status    VARCHAR NOT NULL,     -- 'ACTIVE' / 'STANDBY' / 'DOWN'
    lacp_port_priority INTEGER DEFAULT 32768,
    PRIMARY KEY (lag_id, if_id),
    FOREIGN KEY (lag_id) REFERENCES t_lag(lag_id),
    FOREIGN KEY (if_id) REFERENCES t_interface(if_id)
);
```

#### t_ip_address — IP 地址管理
```sql
CREATE TABLE t_ip_address (
    ip_id            VARCHAR PRIMARY KEY,
    ip_address       VARCHAR NOT NULL,
    ip_version       VARCHAR NOT NULL,    -- 'IPv4' / 'IPv6'
    prefix_length    INTEGER NOT NULL,
    address_type     VARCHAR NOT NULL,    -- 'loopback' / 'interface' / 'management' / 'vip'
    if_id            VARCHAR,
    ne_id            VARCHAR,
    vrf_id           VARCHAR,
    status           VARCHAR NOT NULL,    -- 'ASSIGNED' / 'RESERVED' / 'AVAILABLE'
    FOREIGN KEY (if_id) REFERENCES t_interface(if_id),
    FOREIGN KEY (ne_id) REFERENCES t_network_element(ne_id),
    FOREIGN KEY (vrf_id) REFERENCES t_vrf_instance(vrf_id)
);
```

#### t_interface_ext — 接口扩展
```sql
CREATE TABLE t_interface_ext (
    if_id               VARCHAR PRIMARY KEY,
    mac_address          VARCHAR,
    mtu                  INTEGER DEFAULT 9000,
    duplex               VARCHAR,          -- 'full' / 'half' / 'auto'
    flow_control         VARCHAR,          -- 'send' / 'receive' / 'both' / 'none'
    storm_control_bps    BIGINT,
    port_security        BOOLEAN DEFAULT FALSE,
    errdisable_recovery  BOOLEAN DEFAULT TRUE,
    last_flap_time       TIMESTAMP,
    flap_count_24h       INTEGER DEFAULT 0,
    crc_error_count      BIGINT DEFAULT 0,
    input_error_count    BIGINT DEFAULT 0,
    output_error_count   BIGINT DEFAULT 0,
    FOREIGN KEY (if_id) REFERENCES t_interface(if_id)
);
```

### 3.4 拓扑域（4 表）

#### t_physical_link_ext — 链路扩展
```sql
CREATE TABLE t_physical_link_ext (
    link_id             VARCHAR PRIMARY KEY,
    fiber_type          VARCHAR,          -- 'single_mode' / 'multi_mode'
    fiber_pair_count    INTEGER DEFAULT 1,
    cable_type          VARCHAR,          -- 'aerial' / 'underground' / 'submarine'
    distance_km         DECIMAL(10,2),
    owner               VARCHAR,          -- 运营商/第三方
    lease_expire_date   DATE,
    maintenance_window  VARCHAR,          -- 'SUN 02:00-06:00'
    last_maintenance    DATE,
    FOREIGN KEY (link_id) REFERENCES t_physical_link(link_id)
);
```

#### t_logical_link — 逻辑链路
```sql
CREATE TABLE t_logical_link (
    logical_link_id  VARCHAR PRIMARY KEY,
    link_name        VARCHAR NOT NULL,
    link_type        VARCHAR NOT NULL,    -- 'lag' / 'vlan_trunk' / 'ip_link'
    a_ne_id          VARCHAR NOT NULL,
    a_if_id          VARCHAR,
    z_ne_id          VARCHAR NOT NULL,
    z_if_id          VARCHAR,
    bandwidth_mbps   BIGINT,
    encapsulation    VARCHAR,
    oper_status      VARCHAR NOT NULL,
    underlying_links VARCHAR,             -- 物理链路 ID 列表（逗号分隔）
    FOREIGN KEY (a_ne_id) REFERENCES t_network_element(ne_id),
    FOREIGN KEY (z_ne_id) REFERENCES t_network_element(ne_id)
);
```

#### t_topology_path — 拓扑路径（端到端路径）
```sql
CREATE TABLE t_topology_path (
    path_id          VARCHAR PRIMARY KEY,
    path_name        VARCHAR,
    path_type        VARCHAR NOT NULL,    -- 'explicit' / 'dynamic' / 'segment_list'
    source_ne_id     VARCHAR NOT NULL,
    dest_ne_id       VARCHAR NOT NULL,
    hop_count        INTEGER,
    hop_list         VARCHAR,             -- 有序节点 ID（JSON 数组）
    total_latency_ms DECIMAL(10,3),
    total_bandwidth_mbps BIGINT,
    status           VARCHAR NOT NULL,
    FOREIGN KEY (source_ne_id) REFERENCES t_network_element(ne_id),
    FOREIGN KEY (dest_ne_id) REFERENCES t_network_element(ne_id)
);
```

### 3.5 路由域（5 表）

#### t_bgp_peer — BGP 邻居
```sql
CREATE TABLE t_bgp_peer (
    peer_id          VARCHAR PRIMARY KEY,
    ne_id            VARCHAR NOT NULL,
    peer_ip          VARCHAR NOT NULL,
    peer_as          BIGINT NOT NULL,
    local_as         BIGINT NOT NULL,
    address_family   VARCHAR NOT NULL,    -- 'ipv4_unicast' / 'vpnv4' / 'ipv6_unicast' / 'evpn'
    peer_type        VARCHAR NOT NULL,    -- 'ibgp' / 'ebgp'
    peer_role        VARCHAR,             -- 'route_reflector_client' / 'confederation'
    session_state    VARCHAR NOT NULL,    -- 'ESTABLISHED' / 'IDLE' / 'ACTIVE' / 'OPENSENT'
    uptime_seconds   BIGINT,
    prefixes_received INTEGER,
    prefixes_sent    INTEGER,
    last_error       VARCHAR,
    vrf_id           VARCHAR,
    FOREIGN KEY (ne_id) REFERENCES t_network_element(ne_id),
    FOREIGN KEY (vrf_id) REFERENCES t_vrf_instance(vrf_id)
);
```

#### t_ospf_area — OSPF 区域
```sql
CREATE TABLE t_ospf_area (
    area_id          VARCHAR PRIMARY KEY,
    ne_id            VARCHAR NOT NULL,
    ospf_process_id  INTEGER NOT NULL,
    area_number      VARCHAR NOT NULL,    -- '0.0.0.0' (backbone)
    area_type        VARCHAR NOT NULL,    -- 'normal' / 'stub' / 'nssa' / 'totally_stub'
    interface_count  INTEGER,
    neighbor_count   INTEGER,
    lsa_count        INTEGER,
    spf_run_count    BIGINT,
    FOREIGN KEY (ne_id) REFERENCES t_network_element(ne_id)
);
```

#### t_isis_adjacency — IS-IS 邻接
```sql
CREATE TABLE t_isis_adjacency (
    adjacency_id     VARCHAR PRIMARY KEY,
    ne_id            VARCHAR NOT NULL,
    if_id            VARCHAR NOT NULL,
    neighbor_system_id VARCHAR NOT NULL,
    level            VARCHAR NOT NULL,    -- 'L1' / 'L2' / 'L1L2'
    adjacency_state  VARCHAR NOT NULL,    -- 'UP' / 'INIT' / 'DOWN'
    hold_time_sec    INTEGER,
    metric           INTEGER,
    FOREIGN KEY (ne_id) REFERENCES t_network_element(ne_id),
    FOREIGN KEY (if_id) REFERENCES t_interface(if_id)
);
```

#### t_route_table — 路由表（采样快照）
```sql
CREATE TABLE t_route_table (
    route_id         VARCHAR PRIMARY KEY,
    ne_id            VARCHAR NOT NULL,
    vrf_id           VARCHAR,
    prefix           VARCHAR NOT NULL,    -- '10.0.0.0/24'
    next_hop         VARCHAR NOT NULL,
    protocol         VARCHAR NOT NULL,    -- 'bgp' / 'ospf' / 'isis' / 'static' / 'connected'
    preference       INTEGER,
    metric           BIGINT,
    out_interface     VARCHAR,
    label_stack      VARCHAR,             -- MPLS 标签栈
    collect_time     TIMESTAMP,
    FOREIGN KEY (ne_id) REFERENCES t_network_element(ne_id),
    FOREIGN KEY (vrf_id) REFERENCES t_vrf_instance(vrf_id)
);
```

#### t_bfd_session — BFD 会话
```sql
CREATE TABLE t_bfd_session (
    bfd_session_id   VARCHAR PRIMARY KEY,
    ne_id            VARCHAR NOT NULL,
    local_ip         VARCHAR NOT NULL,
    remote_ip        VARCHAR NOT NULL,
    protocol_binding VARCHAR NOT NULL,    -- 'bgp' / 'ospf' / 'isis' / 'static'
    detect_multiplier INTEGER DEFAULT 3,
    min_tx_interval_ms INTEGER DEFAULT 100,
    min_rx_interval_ms INTEGER DEFAULT 100,
    session_state    VARCHAR NOT NULL,    -- 'UP' / 'DOWN' / 'ADMIN_DOWN'
    up_count         INTEGER DEFAULT 0,
    last_down_time   TIMESTAMP,
    last_down_reason VARCHAR,
    FOREIGN KEY (ne_id) REFERENCES t_network_element(ne_id)
);
```

### 3.6 业务域（12 表）

#### t_l2vpn_service — L2VPN 业务
```sql
CREATE TABLE t_l2vpn_service (
    vpn_id           VARCHAR PRIMARY KEY,
    vpn_name         VARCHAR NOT NULL,
    vpn_type         VARCHAR NOT NULL,    -- 'VPWS' / 'VPLS' / 'EVPN'
    customer_name    VARCHAR NOT NULL,
    service_level    VARCHAR NOT NULL,    -- 'GOLD' / 'SILVER' / 'BRONZE'
    bandwidth_mbps   INTEGER,
    vlan_id          INTEGER,
    mtu              INTEGER DEFAULT 1500,
    status           VARCHAR NOT NULL,    -- 'ACTIVE' / 'INACTIVE' / 'PROVISIONING'
    created_date     DATE,
    contract_expire_date DATE,
    description      VARCHAR
);
```

#### t_pseudowire — 伪线
```sql
CREATE TABLE t_pseudowire (
    pw_id            VARCHAR PRIMARY KEY,
    pw_name          VARCHAR,
    pw_type          VARCHAR NOT NULL,    -- 'ethernet' / 'vlan' / 'atm'
    l2vpn_id         VARCHAR NOT NULL,
    source_ne_id     VARCHAR NOT NULL,
    dest_ne_id       VARCHAR NOT NULL,
    pw_id_local      INTEGER,
    pw_id_remote     INTEGER,
    tunnel_id        VARCHAR,             -- 承载隧道
    control_word     BOOLEAN DEFAULT TRUE,
    oper_status      VARCHAR NOT NULL,
    FOREIGN KEY (l2vpn_id) REFERENCES t_l2vpn_service(vpn_id),
    FOREIGN KEY (source_ne_id) REFERENCES t_network_element(ne_id),
    FOREIGN KEY (dest_ne_id) REFERENCES t_network_element(ne_id),
    FOREIGN KEY (tunnel_id) REFERENCES t_tunnel(tunnel_id)
);
```

#### t_attachment_circuit — 接入电路
```sql
CREATE TABLE t_attachment_circuit (
    ac_id            VARCHAR PRIMARY KEY,
    l2vpn_id         VARCHAR NOT NULL,
    ne_id            VARCHAR NOT NULL,
    if_id            VARCHAR NOT NULL,
    ac_type          VARCHAR NOT NULL,    -- 'port' / 'dot1q' / 'qinq'
    vlan_id          INTEGER,
    bandwidth_mbps   INTEGER,
    oper_status      VARCHAR NOT NULL,
    FOREIGN KEY (l2vpn_id) REFERENCES t_l2vpn_service(vpn_id),
    FOREIGN KEY (ne_id) REFERENCES t_network_element(ne_id),
    FOREIGN KEY (if_id) REFERENCES t_interface(if_id)
);
```

#### t_evpn_instance — EVPN 实例
```sql
CREATE TABLE t_evpn_instance (
    evpn_id          VARCHAR PRIMARY KEY,
    evpn_name        VARCHAR NOT NULL,
    l2vpn_id         VARCHAR,
    evi               INTEGER NOT NULL,    -- EVI (EVPN Instance ID)
    rd               VARCHAR,             -- Route Distinguisher
    rt_import        VARCHAR,             -- Route Target import
    rt_export        VARCHAR,
    mac_limit        INTEGER DEFAULT 65535,
    arp_suppress     BOOLEAN DEFAULT TRUE,
    FOREIGN KEY (l2vpn_id) REFERENCES t_l2vpn_service(vpn_id)
);
```

#### t_sla_template — SLA 模板
```sql
CREATE TABLE t_sla_template (
    sla_id           VARCHAR PRIMARY KEY,
    sla_name         VARCHAR NOT NULL,
    service_level    VARCHAR NOT NULL,    -- 'GOLD' / 'SILVER' / 'BRONZE' / 'PLATINUM'
    max_latency_ms   DECIMAL(10,3),
    max_jitter_ms    DECIMAL(10,3),
    max_packet_loss_pct DECIMAL(5,4),
    min_availability_pct DECIMAL(5,2),
    min_bandwidth_mbps INTEGER,
    measurement_interval_min INTEGER DEFAULT 5,
    violation_threshold_count INTEGER DEFAULT 3,
    penalty_per_violation DECIMAL(10,2),
    description      VARCHAR
);
```

#### t_qos_policy — QoS 策略
```sql
CREATE TABLE t_qos_policy (
    policy_id        VARCHAR PRIMARY KEY,
    policy_name      VARCHAR NOT NULL,
    ne_id            VARCHAR NOT NULL,
    if_id            VARCHAR,
    direction        VARCHAR NOT NULL,    -- 'inbound' / 'outbound'
    classifier_count INTEGER,
    total_bandwidth_kbps BIGINT,
    FOREIGN KEY (ne_id) REFERENCES t_network_element(ne_id),
    FOREIGN KEY (if_id) REFERENCES t_interface(if_id)
);
```

#### t_qos_class — QoS 分类规则
```sql
CREATE TABLE t_qos_class (
    class_id         VARCHAR PRIMARY KEY,
    policy_id        VARCHAR NOT NULL,
    class_name       VARCHAR NOT NULL,    -- 'EF' / 'AF41' / 'BE'
    dscp_value       INTEGER,
    match_protocol   VARCHAR,             -- 'any' / 'tcp' / 'udp'
    action           VARCHAR NOT NULL,    -- 'permit' / 'remark' / 'police' / 'shape'
    bandwidth_pct    INTEGER,
    priority_level   INTEGER,
    FOREIGN KEY (policy_id) REFERENCES t_qos_policy(policy_id)
);
```

#### t_tunnel_ext — 隧道扩展
```sql
CREATE TABLE t_tunnel_ext (
    tunnel_id           VARCHAR PRIMARY KEY,
    signaling_protocol  VARCHAR,          -- 'rsvp-te' / 'sr-te' / 'srv6-te' / 'ldp'
    setup_priority      INTEGER DEFAULT 7,
    hold_priority       INTEGER DEFAULT 0,
    affinity            VARCHAR,          -- 管理属性
    protection_type     VARCHAR,          -- 'none' / '1+1' / 'fast_reroute'
    backup_tunnel_id    VARCHAR,
    path_computation    VARCHAR,          -- 'local' / 'pce' / 'segment_routing'
    binding_sid         VARCHAR,          -- SR Binding SID
    color               INTEGER,          -- SR Policy color
    FOREIGN KEY (tunnel_id) REFERENCES t_tunnel(tunnel_id)
);
```

### 3.7 性能域（12 表）

#### t_twamp_session — TWAMP 测量会话
```sql
CREATE TABLE t_twamp_session (
    session_id       VARCHAR PRIMARY KEY,
    ne_id            VARCHAR NOT NULL,
    sender_ip        VARCHAR NOT NULL,
    reflector_ip     VARCHAR NOT NULL,
    reflector_ne_id  VARCHAR,
    test_type        VARCHAR NOT NULL,    -- 'light' / 'full'
    dscp             INTEGER DEFAULT 0,
    probe_count      INTEGER DEFAULT 100,
    probe_interval_ms INTEGER DEFAULT 100,
    timeout_ms       INTEGER DEFAULT 5000,
    associated_tunnel_id VARCHAR,
    associated_vpn_id    VARCHAR,
    status           VARCHAR NOT NULL,    -- 'ACTIVE' / 'STOPPED' / 'ERROR'
    FOREIGN KEY (ne_id) REFERENCES t_network_element(ne_id),
    FOREIGN KEY (associated_tunnel_id) REFERENCES t_tunnel(tunnel_id)
);
```

#### t_twamp_result — TWAMP 测量结果
```sql
CREATE TABLE t_twamp_result (
    result_id        VARCHAR PRIMARY KEY,
    session_id       VARCHAR NOT NULL,
    collect_time     TIMESTAMP NOT NULL,
    round_trip_delay_us INTEGER,
    oneway_delay_fwd_us INTEGER,          -- 正向单向时延
    oneway_delay_rev_us INTEGER,          -- 反向单向时延
    jitter_fwd_us    INTEGER,
    jitter_rev_us    INTEGER,
    packet_loss_fwd_pct DECIMAL(5,4),
    packet_loss_rev_pct DECIMAL(5,4),
    probe_sent       INTEGER,
    probe_received   INTEGER,
    FOREIGN KEY (session_id) REFERENCES t_twamp_session(session_id)
);
```

#### t_ifit_flow — IFIT 流定义
```sql
CREATE TABLE t_ifit_flow (
    flow_id          VARCHAR PRIMARY KEY,
    ne_id            VARCHAR NOT NULL,
    flow_name        VARCHAR,
    src_ip           VARCHAR,
    dst_ip           VARCHAR,
    dscp             INTEGER,
    protocol         VARCHAR,             -- 'tcp' / 'udp' / 'any'
    direction        VARCHAR NOT NULL,    -- 'ingress' / 'egress'
    measurement_type VARCHAR NOT NULL,    -- 'delay' / 'loss' / 'both'
    interval_ms      INTEGER DEFAULT 1000,
    status           VARCHAR NOT NULL,
    FOREIGN KEY (ne_id) REFERENCES t_network_element(ne_id)
);
```

#### t_ifit_result — IFIT 测量结果
```sql
CREATE TABLE t_ifit_result (
    result_id        VARCHAR PRIMARY KEY,
    flow_id          VARCHAR NOT NULL,
    collect_time     TIMESTAMP NOT NULL,
    e2e_delay_us     INTEGER,
    hop_count        INTEGER,
    hop_delays_us    VARCHAR,             -- JSON 数组：[120, 85, 230]
    path_nodes       VARCHAR,             -- JSON 数组：['NE-001', 'NE-003', 'NE-005']
    packet_count     BIGINT,
    drop_count       INTEGER,
    drop_node        VARCHAR,             -- 丢包发生的节点
    drop_reason      VARCHAR,             -- 'queue_full' / 'acl_deny' / 'ttl_expired'
    FOREIGN KEY (flow_id) REFERENCES t_ifit_flow(flow_id)
);
```

#### t_interface_counter — 接口计数器（高频采样）
```sql
CREATE TABLE t_interface_counter (
    counter_id       VARCHAR PRIMARY KEY,
    if_id            VARCHAR NOT NULL,
    ne_id            VARCHAR NOT NULL,
    collect_time     TIMESTAMP NOT NULL,
    in_octets        BIGINT,
    out_octets       BIGINT,
    in_packets       BIGINT,
    out_packets      BIGINT,
    in_unicast       BIGINT,
    out_unicast      BIGINT,
    in_multicast     BIGINT,
    out_multicast    BIGINT,
    in_broadcast     BIGINT,
    out_broadcast    BIGINT,
    in_errors        BIGINT,
    out_errors       BIGINT,
    in_discards      BIGINT,
    out_discards     BIGINT,
    crc_errors       BIGINT,
    FOREIGN KEY (if_id) REFERENCES t_interface(if_id),
    FOREIGN KEY (ne_id) REFERENCES t_network_element(ne_id)
);
```

#### t_optical_perf — 光模块性能
```sql
CREATE TABLE t_optical_perf (
    perf_id          VARCHAR PRIMARY KEY,
    module_id        VARCHAR NOT NULL,
    collect_time     TIMESTAMP NOT NULL,
    tx_power_dbm     DECIMAL(6,2),
    rx_power_dbm     DECIMAL(6,2),
    temperature_c    DECIMAL(6,2),
    voltage_v        DECIMAL(6,3),
    bias_current_ma  DECIMAL(8,3),
    tx_power_alarm   BOOLEAN DEFAULT FALSE,
    rx_power_alarm   BOOLEAN DEFAULT FALSE,
    FOREIGN KEY (module_id) REFERENCES t_optical_module(module_id)
);
```

### 3.8 告警域（6 表）

#### t_alarm — 当前告警
```sql
CREATE TABLE t_alarm (
    alarm_id         VARCHAR PRIMARY KEY,
    ne_id            VARCHAR NOT NULL,
    if_id            VARCHAR,
    alarm_source     VARCHAR NOT NULL,    -- 对象标识
    alarm_type       VARCHAR NOT NULL,    -- 'communication' / 'quality_of_service' / 'processing_error' / 'equipment' / 'environmental'
    severity         VARCHAR NOT NULL,    -- 'CRITICAL' / 'MAJOR' / 'MINOR' / 'WARNING'
    probable_cause   VARCHAR NOT NULL,    -- 'link_failure' / 'power_problem' / 'cpu_threshold'
    alarm_text       VARCHAR NOT NULL,
    raised_time      TIMESTAMP NOT NULL,
    acked            BOOLEAN DEFAULT FALSE,
    acked_by         VARCHAR,
    acked_time       TIMESTAMP,
    cleared          BOOLEAN DEFAULT FALSE,
    cleared_time     TIMESTAMP,
    FOREIGN KEY (ne_id) REFERENCES t_network_element(ne_id),
    FOREIGN KEY (if_id) REFERENCES t_interface(if_id)
);
```

#### t_alarm_history — 告警历史
```sql
CREATE TABLE t_alarm_history (
    history_id       VARCHAR PRIMARY KEY,
    alarm_id         VARCHAR NOT NULL,
    ne_id            VARCHAR NOT NULL,
    alarm_type       VARCHAR NOT NULL,
    severity         VARCHAR NOT NULL,
    probable_cause   VARCHAR NOT NULL,
    alarm_text       VARCHAR NOT NULL,
    raised_time      TIMESTAMP NOT NULL,
    cleared_time     TIMESTAMP,
    duration_min     INTEGER,
    root_cause_id    VARCHAR,             -- 关联的根因告警
    affected_services VARCHAR,            -- 受影响的 VPN 业务 ID 列表
    FOREIGN KEY (ne_id) REFERENCES t_network_element(ne_id)
);
```

#### t_alarm_rule — 告警规则
```sql
CREATE TABLE t_alarm_rule (
    rule_id          VARCHAR PRIMARY KEY,
    rule_name        VARCHAR NOT NULL,
    target_type      VARCHAR NOT NULL,    -- 'ne' / 'interface' / 'tunnel' / 'vpn'
    metric_name      VARCHAR NOT NULL,    -- 'cpu_usage_avg_pct' / 'in_bandwidth_usage_pct'
    condition        VARCHAR NOT NULL,    -- 'gt' / 'lt' / 'eq'
    threshold_warning  DECIMAL(10,3),
    threshold_minor  DECIMAL(10,3),
    threshold_major  DECIMAL(10,3),
    threshold_critical DECIMAL(10,3),
    duration_min     INTEGER DEFAULT 5,   -- 持续 N 分钟才触发
    enabled          BOOLEAN DEFAULT TRUE
);
```

#### t_event — 操作事件
```sql
CREATE TABLE t_event (
    event_id         VARCHAR PRIMARY KEY,
    ne_id            VARCHAR,
    event_type       VARCHAR NOT NULL,    -- 'config_change' / 'reboot' / 'failover' / 'link_flap' / 'user_login'
    event_source     VARCHAR NOT NULL,    -- 'system' / 'user' / 'nms'
    event_detail     VARCHAR NOT NULL,
    event_time       TIMESTAMP NOT NULL,
    user_name        VARCHAR,
    ip_address       VARCHAR,
    FOREIGN KEY (ne_id) REFERENCES t_network_element(ne_id)
);
```

### 3.9 配置域（4 表）

#### t_config_baseline — 配置基线
```sql
CREATE TABLE t_config_baseline (
    baseline_id      VARCHAR PRIMARY KEY,
    ne_id            VARCHAR NOT NULL,
    config_type      VARCHAR NOT NULL,    -- 'running' / 'startup' / 'golden'
    config_hash      VARCHAR NOT NULL,    -- MD5/SHA256
    config_size_bytes INTEGER,
    captured_time    TIMESTAMP NOT NULL,
    captured_by      VARCHAR,             -- 'auto' / 'manual'
    is_compliant     BOOLEAN,
    drift_count      INTEGER DEFAULT 0,   -- 与 golden 的差异行数
    FOREIGN KEY (ne_id) REFERENCES t_network_element(ne_id)
);
```

#### t_config_change — 配置变更记录
```sql
CREATE TABLE t_config_change (
    change_id        VARCHAR PRIMARY KEY,
    ne_id            VARCHAR NOT NULL,
    change_type      VARCHAR NOT NULL,    -- 'add' / 'modify' / 'delete'
    section          VARCHAR,             -- 'interface' / 'bgp' / 'acl' / 'qos'
    before_value     VARCHAR,
    after_value      VARCHAR,
    changed_by       VARCHAR NOT NULL,    -- 用户名或 'nms'
    changed_time     TIMESTAMP NOT NULL,
    change_ticket    VARCHAR,             -- 关联工单号
    rollback_id      VARCHAR,             -- 可回滚到的基线 ID
    FOREIGN KEY (ne_id) REFERENCES t_network_element(ne_id)
);
```

## 4. 数据量规划

| 表类型 | 表数 | 单表行数 | 说明 |
|--------|------|---------|------|
| 存量主表 | ~15 | 25-500 | 站点/设备/接口/链路等 |
| 存量扩展表 | ~10 | 同主表 | `_ext` 分表，1:1 关联 |
| 路由/协议表 | ~5 | 100-1000 | BGP 邻居/OSPF/BFD 等 |
| 业务表 | ~12 | 30-200 | VPN/PW/AC/QoS 等 |
| 性能表（时序） | ~12 | 5000-50000 | 按采集周期（15min/1h）累积 |
| 告警/事件表 | ~6 | 500-5000 | 告警历史按时间增长 |
| 配置表 | ~4 | 50-500 | 基线/变更记录 |
| **合计** | **~65** | | **预计 2000-2500 列** |

## 5. 扩表实施步骤

### Step 1: DDL 定稿
- 根据本文档的表结构定稿最终 DDL
- 确认列名命名规范（保持与现有 14 表一致的 snake_case）
- 确认外键关系图

### Step 2: Mock 数据生成
- 复用现有 `telecom/scripts/generate_mock_data.py` 的模式
- 新增表的数据生成逻辑
- 确保外键约束满足（先生成主表再生成从表）
- 性能表的时间序列要合理（有趋势、有波动、有异常点）

### Step 3: 评测集扩展
- 按子域分组生成 question-SQL 对
- 覆盖新增的跨域查询（如"告警关联 VPN 业务"、"IFIT 路径追踪"）
- 难度梯度：单表 → 双表 JOIN → 多表关联 → 跨域分析

### Step 4: 验证
- 跑 eval 框架确认 Qwen 32B 在 65 表上的表现
- 对比 14 表 vs 65 表的准确率差异 — 这就是课题一的核心实验数据
