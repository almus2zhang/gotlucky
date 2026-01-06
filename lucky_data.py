import asyncio
from playwright.async_api import async_playwright

async def get_lucky_services(url, username, password, server_name="lucky"):
    services = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 720},
            ignore_https_errors=True
        )
        page = await context.new_page()

        # 确定目标 Web 服务页面的 URL
        lucky_web_url = url.rstrip('/') + "/#/web"
        print(f"[*] {server_name} 正在尝试访问: {lucky_web_url}")
        
        try:
            # 增加超时并使用 networkidle2 的替代逻辑：等待基础 DOM 加载
            await page.goto(lucky_web_url, wait_until="load", timeout=30000)
            # 给页面 2 秒时间渲染基础框架
            await page.wait_for_timeout(2000)
        except Exception as e:
            print(f"[!] {server_name} 初步访问异常: {e}")

        # 1. 自动判断当前状态：是登录页还是主界面？
        # 等待密码框 (登录) 或 侧边栏 (主界面) 其中之一出现
        print(f"[*] {server_name} 正在检测页面状态...")
        try:
            await page.wait_for_selector('input[type="password"], .el-aside, .main-container, .base-layout', timeout=15000)
        except:
            print(f"[!] {server_name} 页面加载后未检测到已知特征，尝试强行继续")

        is_login_required = await page.query_selector('input[type="password"]') or "/login" in page.url
        
        if is_login_required:
            print(f"[*] {server_name} 检测到需要登录...")
            try:
                # 寻找输入框
                user_input = await page.wait_for_selector('input[type="text"], input[placeholder*="用户"], .el-input__inner', timeout=5000)
                pass_input = await page.query_selector('input[type="password"]')
                
                if user_input and pass_input:
                    await user_input.fill(username)
                    await pass_input.fill(password)
                    
                    login_btn = await page.query_selector('button.login-button, button.el-button--primary, button:has-text("登录")')
                    if login_btn:
                        await login_btn.click()
                        print(f"[*] {server_name} 已提交登录表单")
                        
                        # 等待主界面加载
                        await page.wait_for_selector('.el-aside, .main-container, .base-layout', timeout=20000)
                        print(f"[+] {server_name} 登录成功")
                        
                        # 重定向到目标页面 (Hash 路由有时需要二次确认)
                        if "/web" not in page.url:
                            print(f"[*] {server_name} 强制跳转到 Web 服务配置...")
                            await page.goto(lucky_web_url, wait_until="domcontentloaded")
            except Exception as e:
                print(f"[!] {server_name} 登录操作失败: {e}")
                await page.screenshot(path=f"debug_{server_name}_login_error.png")

        # 2. 确保在目标页并等待条目加载
        if "/web" not in page.url:
             await page.goto(lucky_web_url, wait_until="load")
             await page.wait_for_timeout(3000)

        # 4. 等待渲染并展开子规则 (关键：许多服务隐藏在子规则中)
        print(f"[*] {server_name} 正在准备数据展开...")
        try:
            # 等待基本的 Web 规则界面特征
            await page.wait_for_selector('.el-main, .main-container', timeout=15000)
            
            # 找到所有的“显示所有子规则”按钮并点击
            expand_btns = await page.query_selector_all('button:has-text("显示所有子规则"), .el-button:has-text("显示")')
            if expand_btns:
                print(f"[*] {server_name} 发现 {len(expand_btns)} 处可展开的子规则，正在展开...")
                for btn in expand_btns:
                    try:
                        await btn.click()
                        await page.wait_for_timeout(500)
                    except: pass
            
            # 给 5 秒让所有内容（包括子规则）加载完毕
            await page.wait_for_timeout(5000)
        except:
             print(f"[!] {server_name} 展开子规则阶段超时，尝试继续抓取")

        # 5. 寻找规则行 - 采用更具包容性的策略
        # 我们寻找包含协议、箭头、或“日志/操作”按钮的区块
        # 很多时候最小容器是带有特定 class 的 div
        rows = []
        selectors = [
            '.el-table__row', 
            '.rule-item', 
            '.web-rule-item',
            'div.rule-row', 
            '.el-card__body', # 针对卡片式布局
            'div:has-text("➔")',
            'div:has-text("->")'
        ]
        
        for sel in selectors:
            try:
                found = await page.query_selector_all(sel)
                if len(found) > 1:
                    rows = found
                    print(f"[*] {server_name} 使用选择器: {sel} (候选行: {len(rows)})")
                    break
            except: continue

        if not rows:
            print(f"[*] {server_name} 使用地毯式 div 扫描")
            rows = await page.query_selector_all('.el-main div')

        unique_services = {}
        import re

        for idx, row in enumerate(rows):
            try:
                text = await row.inner_text()
                if not text.strip() or '添加Web' in text or '显示所有' in text: continue

                # 1. 提取前端域名和后端地址
                # 策略：优先通过分割符判定逻辑关系 (源 ➔ 目标)
                src = None
                target = None
                
                # 常见的 Lucky 分隔符
                separators = ['➔', '->']
                found_sep = next((s for s in separators if s in text), None)
                
                if found_sep:
                    s_parts = text.split(found_sep)
                    left_text = s_parts[0].strip()
                    right_text = s_parts[1].strip()
                    
                    # 后端目标：通常是分隔符右侧的第一块文本或 URL
                    # 允许纯文字，例如 "文件服务"
                    target = right_text.split('\n')[0].split('|')[0].strip()
                    
                    # 前端域名：在分隔符左侧寻找最像域名的片段
                    # 我们过滤出所有符合地址特征的，取最后一个作为主域名
                    left_tokens = [t.strip() for t in re.split(r'\s+|\|', left_text) if len(t.strip()) > 2]
                    addr_tokens = [t for t in left_tokens if '.' in t or '://' in t or 'localhost' in t]
                    src = addr_tokens[-1] if addr_tokens else (left_tokens[-1] if left_tokens else "")
                else:
                    # 兜底方案：正则提取所有地址并一头一尾匹配
                    pattern = r'https?://[^\s\t\n]+|[\w\.-]+\.[a-zA-Z]{2,}(?::\d+)?|127\.0\.0\.1:\d+|localhost:\d+'
                    found_parts = re.findall(pattern, text)
                    found_parts = [p.strip().rstrip(':').rstrip('.') for p in found_parts if len(p.strip()) > 3]
                    
                    if len(found_parts) >= 2:
                        src = found_parts[0]
                        target = found_parts[-1]
                    elif len(found_parts) == 1:
                        src = found_parts[0]
                        # 尝试从之后的文本中寻找后端描述
                        after_src = text.split(src)[-1].strip()
                        target = after_src.split('\n')[0].split('|')[0].strip()
                
                if src and target and target.strip():
                    domain_part = src.split('://')[-1].split('/')[0] if '://' in src else src
                    # 过滤掉常见的系统占位符
                    if domain_part in ['127.0.0.1', 'localhost', '0.0.0.0', '::']:
                        # 如果能拿到更多信息则尝试更正 (在 found_parts 场景下)
                        pass 

                    if domain_part and ('.' in domain_part or 'localhost' in domain_part or len(domain_part) > 3):
                        if domain_part not in unique_services:
                            unique_services[domain_part] = {
                                "domain": domain_part,
                                "protocol": "https" if "https://" in src else "http",
                                "internal_addr": target.strip()
                            }
            except:
                continue

        services = list(unique_services.values())
        print(f"[*] {server_name} 最终提取到 {len(services)} 条服务规则")
        
        if not services and server_name == "bwg-lucky":
            # 如果依然抓不到且是重点服务器，记录部分 HTML 结构
            page_content = await page.inner_text('.el-main')
            print(f"DEBUG {server_name} .el-main 文本预览: {page_content[:200]}...")

        await browser.close()
    return services

if __name__ == "__main__":
    # Test
    # services = asyncio.run(get_lucky_services("https://lucky.example.com", "admin", "password"))
    # print(services)
    pass
