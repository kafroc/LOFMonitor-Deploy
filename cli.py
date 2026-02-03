# -*- coding: utf-8 -*-
"""
LOF基金溢价监控程序 - 终端交互模块
"""

import sys
import time
import threading
from config import config
from data_fetcher import get_all_fund_data
from calculator import calculate_premium_discount, get_status
from notifier import send_dingtalk_alert, format_alert_message
from logger_util import log_alert

import unicodedata

def align_text(text, width, align='left'):
    """处理包含中文字符的字符串对齐"""
    text = str(text)
    # 计算实际显示宽度 (中文字符占2，英文字符占1)
    d_width = 0
    for char in text:
        if unicodedata.east_asian_width(char) in ('W', 'F'):
            d_width += 2
        else:
            d_width += 1
    
    padding = max(0, width - d_width)
    if align == 'left':
        return text + ' ' * padding
    elif align == 'right':
        return ' ' * padding + text
    else:
        left = padding // 2
        return ' ' * left + text + ' ' * (padding - left)

class LOFMonitorCLI:
    def __init__(self):
        self.running = False
        self.monitor_thread = None
        
    def start(self):
        """启动终端交互"""
        print("=" * 50)
        print("   LOF基金溢价监控系统 - 终端模式")
        print("=" * 50)
        
        while True:
            self.print_menu()
            choice = input("请输入选项 (1-3): ").strip()
            
            if choice == "1":
                self.show_config()
            elif choice == "2":
                self.modify_config()
            elif choice == "3":
                self.start_monitoring()
                print("执行完毕，退出程序...")
                self.running = False
                sys.exit(0)
            else:
                print("无效选项，请重新输入")
    
    def print_menu(self):
        print("\n[主菜单]")
        print("1. 查看当前配置")
        print("2. 修改配置")
        print("3. 开始监控")
    
    def show_config(self):
        print("\n[当前配置]")
        print(f"溢价阈值: {config.get('premium_threshold')}%")
        print(f"折价阈值: {config.get('discount_threshold')}%")
        print(f"钉钉Webhook: {config.get('dingtalk_webhook') or '未设置'}")
        
    def modify_config(self):
        print("\n[修改配置]")
        print("直接回车保持原值，阈值输入数字不需加%")
        
        # 修改溢价阈值
        val = input(f"溢价阈值 ({config.get('premium_threshold')}%): ").strip()
        if val:
            try:
                config.set("premium_threshold", float(val))
                print("溢价阈值已更新")
            except ValueError:
                print("输入无效，未修改")
                
        # 修改折价阈值
        val = input(f"折价阈值 ({config.get('discount_threshold')}%): ").strip()
        if val:
            try:
                config.set("discount_threshold", float(val))
                print("折价阈值已更新")
            except ValueError:
                print("输入无效，未修改")
                
        # 修改Webhook
        val = input(f"钉钉Webhook ({config.get('dingtalk_webhook') or '空'}): ").strip()
        if val:
            config.set("dingtalk_webhook", val)
            print("Webhook已更新")
            
        # 修改Secret
        val = input(f"钉钉密钥 ({'***' if config.get('dingtalk_secret') else '空'}): ").strip()
        if val:
            config.set("dingtalk_secret", val)
            print("密钥已更新")
            
    def start_monitoring(self):
        print("\n[开始监控]")
        self.run_monitor_cycle()
            
    def run_monitor_cycle(self):
        """执行一次监控循环"""
        print(f"\n正在刷新数据 ({time.strftime('%H:%M:%S')})...")
        
        threshold_premium = config.get("premium_threshold")
        threshold_discount = config.get("discount_threshold")
        
        # 定义列宽
        w_code, w_name, w_mkt, w_nav, w_pre, w_dis, w_stat, w_fstate = 8, 20, 8, 8, 10, 10, 10, 20
        
        # 打印表头
        header = (
            align_text('代码', w_code) + 
            align_text('名称', w_name) + 
            align_text('场内', w_mkt) + 
            align_text('净值', w_nav) + 
            align_text('溢价率', w_pre) + 
            align_text('折价率', w_dis) + 
            align_text('状态', w_stat) + 
            align_text('基金状态', w_fstate)
        )
        print("-" * 100)
        print(header)
        print("-" * 100)
        
        count_container = [0]  # 使用列表以在回调中修改计数
        
        def on_fund_received(fund):
            code = fund['code']
            name = fund['name']
            market_price = fund['market_price']
            nav_price = fund['nav_price']
            f_state = fund.get('fund_state', '')
            
            # 计算溢价/折价率
            premium_rate, discount_rate = calculate_premium_discount(market_price, nav_price)
            
            # 判断状态
            status = get_status(premium_rate, discount_rate, threshold_premium, threshold_discount)
            
            if status in ['premium_alert', 'discount_alert']:
                count_container[0] += 1
                
                # 格式化数据
                p_rate_str = f"{premium_rate:.2f}%" if premium_rate is not None else "N/A"
                d_rate_str = f"{discount_rate:.2f}%" if discount_rate is not None else "N/A"
                m_price_str = f"{market_price:.4f}" if market_price else "N/A"
                n_price_str = f"{nav_price:.4f}" if nav_price else "N/A"
                status_text = "⚠️ 溢价" if status == 'premium_alert' else "⚠️ 折价"
                
                # 构建对齐行
                row = (
                    align_text(code, w_code) +
                    align_text(name[:15], w_name) + # 限制名称长度防干扰
                    align_text(m_price_str, w_mkt) +
                    align_text(n_price_str, w_nav) +
                    align_text(p_rate_str, w_pre) +
                    align_text(d_rate_str, w_dis) +
                    align_text(status_text, w_stat) +
                    align_text(f_state, w_fstate)
                )
                
                # 打印单行结果 (加上\r清空当前进度行)
                print(f"\r{row}")
                
                # 触发告警
                alert_type = 'premium' if status == 'premium_alert' else 'discount'
                rate = premium_rate if alert_type == 'premium' else discount_rate
                threshold = threshold_premium if alert_type == 'premium' else threshold_discount
                
                # 记录日志
                log_alert(code, name, alert_type, rate, threshold)
                
                # 发送钉钉 (每日去重由 notifier.py 和 config.py 处理)
                if not config.is_fund_alerted(code):
                    msg = format_alert_message(code, name, alert_type, rate, market_price, nav_price, f_state)
                    send_dingtalk_alert(config.get("dingtalk_webhook"), config.get("dingtalk_secret"), msg, fund_code=code)
 
        def print_progress(current, total, name, fund_data):
            m_price = fund_data.get('market_price')
            n_price = fund_data.get('nav_price')
            p_rate_str = "N/A"
            if m_price and n_price and n_price != 0:
                p_rate = (m_price - n_price) / n_price * 100
                p_rate_str = f"{p_rate:.2f}%"
            
            print(f"\r正在获取数据: {current}/{total} ({fund_data['code']} {name[:15]} 场内：{m_price or 'N/A'} 净值：{n_price or 'N/A'} 溢价率：{p_rate_str}) 状态：{fund_data['fund_state']}", end="", flush=True)

        # 获取数据并传入回调
        get_all_fund_data(
            progress_callback=print_progress,
            data_callback=on_fund_received
        )
        
        print("\n" + "-" * 100)
        if count_container[0] == 0:
            print("没有发现超过阈值的基金")
