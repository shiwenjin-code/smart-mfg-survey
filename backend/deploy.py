"""Railway 全自动部署脚本"""
import httpx, json, sys

TOKEN = "4955a5f6-5be2-4d60-994a-59353b11bc40"
API = "https://backboard.railway.app/graphql/v2"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
PROJECT_ID = "a8a74c0f-c439-4a5c-86fd-e9c795c748b2"
SERVICE_ID = "3c5a0c8b-cb98-4951-805a-556d798ca20f"

def gql(query, variables=None, label=""):
    payload = {"query": query, "variables": variables or {}}
    r = httpx.post(API, json=payload, headers=HEADERS, timeout=30)
    d = r.json()
    if "errors" in d:
        print(f"[{label}] GraphQL Error:")
        for e in d["errors"]:
            print(f"  - {e.get('message','?')}")
    return d.get("data", {})

# ========================================================
# Step 1: 查询环境和实例
# ========================================================
print("Step 1: 查询环境信息...")
q1 = """
query ($pid: String!) {
  project(id: $pid) {
    environments { edges { node { id name } } }
    services { edges { node { id name serviceInstances { edges { node { id } } } } } }
  }
}
"""
data = gql(q1, {"pid": PROJECT_ID}, "Query env")
proj = data.get("project", {})

envs = proj.get("environments", {}).get("edges", [])
if not envs:
    print("❌ 没找到环境！")
    sys.exit(1)
env_id = envs[0]["node"]["id"]
print(f"  环境: {envs[0]['node']['name']} ({env_id})")

svcs = proj.get("services", {}).get("edges", [])
instance_id = ""
for s in svcs:
    insts = s["node"].get("serviceInstances", {}).get("edges", [])
    if insts:
        instance_id = insts[0]["node"]["id"]
print(f"  实例: {instance_id}")

# ========================================================
# Step 2: 设置环境变量
# ========================================================
print("\nStep 2: 配置环境变量...")
env_vars = [
    ("LLM_API_KEY", "sk-d6219cf1ff7a4fbdbfb1b6f619c3dba4"),
    ("LLM_BASE_URL", "https://api.deepseek.com/v1"),
    ("LLM_MODEL", "deepseek-chat"),
]

for name, value in env_vars:
    q2 = """
    mutation ($input: VariableUpsertInput!) {
      variableUpsert(input: $input)
    }
    """
    gql(q2, {
        "input": {
            "projectId": PROJECT_ID,
            "environmentId": env_id,
            "serviceId": SERVICE_ID,
            "name": name,
            "value": value
        }
    }, f"Set {name}")
    print(f"  ✅ {name} = ***")

# ========================================================
# Step 3: 触发部署
# ========================================================
print("\nStep 3: 触发部署...")
q3 = """
mutation ($input: DeploymentTriggerCreateInput!) {
  deploymentTriggerCreate(input: $input) {
    id
    status
  }
}
"""
data = gql(q3, {
    "input": {
        "serviceId": SERVICE_ID,
        "environmentId": env_id
    }
}, "Deploy")
dep = data.get("deploymentTriggerCreate", {})
print(f"  部署ID: {dep.get('id','?')}")
print(f"  状态: {dep.get('status','?')}")

# ========================================================
# Step 4: 查询域名
# ========================================================
print("\nStep 4: 查询访问地址...")
q4 = """
query ($pid: String!) {
  project(id: $pid) {
    services { edges { node { id name serviceInstances { edges { node { domains { serviceDomains { domain } } } } } } } }
  }
}
"""
data = gql(q4, {"pid": PROJECT_ID}, "Query domains")
try:
    for s in data.get("project",{}).get("services",{}).get("edges",[]):
        for i in s["node"].get("serviceInstances",{}).get("edges",[]):
            domains = i["node"].get("domains",{}).get("serviceDomains",[])
            for d in domains:
                url = f"https://{d['domain']}"
                print(f"\n{'='*50}")
                print(f"📋 问卷端: {url}/")
                print(f"📊 管理后台: {url}/admin")
                print(f"{'='*50}")
except Exception as e:
    print(f"域名查询: {e}")
    print("服务部署中，请稍后到 Railway 仪表板查看域名")

print("\n✅ 部署完成！")
