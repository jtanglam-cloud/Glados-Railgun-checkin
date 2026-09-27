import os
import sys
import time
import requests


# =========================
# 配置
# =========================

COOKIES = os.getenv("GLADOS_COOKIES", "")
PUSHDEER_SENDKEY = os.getenv("PUSHDEER_SENDKEY", "")
EXCHANGE_PLAN = os.getenv("GLADOS_EXCHANGE_PLAN", "plan500")

DOMAINS = [
    "glados.cloud",
    "railgun.info",
]

MAX_RETRY = 3
REQUEST_TIMEOUT = 30


# =========================
# Cookie
# =========================

def parse_cookies():
    cookies = []

    for item in COOKIES.splitlines():
        item = item.strip()

        if not item:
            continue

        # 支持：
        # domain=xxx
        # domain:xxx
        if "=" in item:
            domain, cookie = item.split("=", 1)
        elif ":" in item:
            domain, cookie = item.split(":", 1)
        else:
            continue

        domain = domain.strip()
        cookie = cookie.strip()

        if domain and cookie:
            cookies.append({
                "domain": domain,
                "cookie": cookie
            })

    return cookies


# =========================
# HTTP 请求
# =========================

def request_with_retry(session, method, url, **kwargs):
    """
    网络错误 / 429 / 502 / 503 / 504 自动重试。
    """

    for attempt in range(1, MAX_RETRY + 1):

        try:
            response = session.request(
                method,
                url,
                timeout=REQUEST_TIMEOUT,
                **kwargs
            )

            print(
                f"[HTTP] {method} {url} -> "
                f"{response.status_code}"
            )

            # 成功
            if 200 <= response.status_code < 300:
                return response

            # 可以重试的状态
            if response.status_code in (429, 500, 502, 503, 504):

                retry_after = response.headers.get("Retry-After")

                try:
                    wait_time = int(retry_after)
                except (TypeError, ValueError):
                    wait_time = attempt * 30

                # 防止服务器返回一个超长等待时间
                wait_time = min(wait_time, 120)

                if attempt < MAX_RETRY:
                    print(
                        f"[RETRY] {response.status_code}，"
                        f"{wait_time} 秒后第 {attempt + 1} 次尝试"
                    )

                    time.sleep(wait_time)
                    continue

            # 其他 HTTP 错误直接结束
            print(
                f"[ERROR] HTTP {response.status_code}: "
                f"{response.text[:300]}"
            )

            return response

        except requests.RequestException as e:

            print(
                f"[NETWORK ERROR] 第 {attempt}/{MAX_RETRY} 次: {e}"
            )

            if attempt < MAX_RETRY:
                wait_time = attempt * 15

                print(
                    f"[RETRY] {wait_time} 秒后重试"
                )

                time.sleep(wait_time)

    return None


# =========================
# 签到
# =========================

def checkin(session, domain):
    url = f"https://{domain}/api/user/checkin"

    print(f"\n[CHECKIN] {domain}")

    response = request_with_retry(
        session,
        "POST",
        url,
        json={}
    )

    if response is None:
        print(f"[FAIL] {domain} 签到请求失败")
        return False

    if not (200 <= response.status_code < 300):
        print(
            f"[FAIL] {domain} 签到失败，"
            f"HTTP {response.status_code}"
        )
        return False

    try:
        data = response.json()
        print(f"[RESULT] {data}")
    except Exception:
        print(f"[RESULT] {response.text[:500]}")

    print(f"[SUCCESS] {domain} 签到请求完成")
    return True


# =========================
# 积分
# =========================

def get_points(session, domain):
    url = f"https://{domain}/api/user/status"

    print(f"[POINTS] 查询 {domain}")

    response = request_with_retry(
        session,
        "GET",
        url
    )

    if response is None:
        return

    if response.status_code != 200:
        print(
            f"[POINTS] 查询失败 HTTP {response.status_code}"
        )
        return

    try:
        print(f"[POINTS RESULT] {response.json()}")
    except Exception:
        print(f"[POINTS RESULT] {response.text[:500]}")


# =========================
# 兑换
# =========================

def exchange(session, domain):
    if not EXCHANGE_PLAN:
        print("[EXCHANGE] 未设置兑换计划，跳过")
        return

    url = f"https://{domain}/api/user/exchange"

    print(
        f"[EXCHANGE] {domain} "
        f"plan={EXCHANGE_PLAN}"
    )

    response = request_with_retry(
        session,
        "POST",
        url,
        json={
            "plan": EXCHANGE_PLAN
        }
    )

    if response is None:
        return

    try:
        print(f"[EXCHANGE RESULT] {response.json()}")
    except Exception:
        print(
            f"[EXCHANGE RESULT] "
            f"{response.text[:500]}"
        )


# =========================
# 单个 Cookie
# =========================

def process_cookie(cookie_info):

    domain_cookie = cookie_info["domain"]
    cookie = cookie_info["cookie"]

    print("\n==============================")
    print(f"处理 Cookie: {domain_cookie}")
    print("==============================")

    session = requests.Session()

    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/140.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Referer": f"https://{domain_cookie}/",
    })

    session.cookies.set(
        "koa.sid",
        cookie,
        domain=domain_cookie
    )

    success_count = 0

    for domain in DOMAINS:

        print(
            f"\n---------- {domain} ----------"
        )

        # =========================
        # 最重要：
        # 签到失败以后不再继续积分/兑换
        # =========================

        ok = checkin(session, domain)

        if not ok:
            print(
                f"[SKIP] {domain} 签到失败，"
                f"跳过积分和兑换"
            )
            continue

        success_count += 1

        # 签到成功才继续
        get_points(session, domain)

        # 暂时保留兑换功能
        # 如果不需要自动兑换，可以注释掉
        exchange(session, domain)

    return success_count


# =========================
# 主程序
# =========================

def main():

    print("================================")
    print("GLaDOS 自动签到")
    print("================================")

    if not COOKIES:
        print("[ERROR] GLADOS_COOKIES 未设置")
        return 1

    if not PUSHDEER_SENDKEY:
        print(
            "[INFO] PUSHDEER_SENDKEY 未设置，"
            "不发送 PushDeer 通知"
        )

    print(
        f"[INFO] EXCHANGE_PLAN = {EXCHANGE_PLAN}"
    )

    cookies = parse_cookies()

    print(
        f"[INFO] 共加载 {len(cookies)} 个 Cookie"
    )

    if not cookies:
        print("[ERROR] 没有有效 Cookie")
        return 1

    total_success = 0

    for cookie_info in cookies:

        try:
            total_success += process_cookie(
                cookie_info
            )

        except Exception as e:

            # 一个账号异常，不影响其他账号
            print(
                f"[ERROR] Cookie 处理异常: {e}"
            )

            continue

    print("\n================================")
    print(
        f"[SUMMARY] 成功签到接口次数："
        f"{total_success}"
    )
    print("================================")

    # 一个都没成功 → GitHub Actions 标记失败
    if total_success == 0:
        print(
            "[FINAL] 所有签到均失败"
        )
        return 1

    print(
        "[FINAL] 至少一个签到成功"
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
