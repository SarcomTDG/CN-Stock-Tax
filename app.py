from flask import Flask, render_template, request, jsonify
from longport.openapi import TradeContext, Config
from datetime import datetime, timedelta
import pandas as pd

app = Flask(__name__)

# --- 配置长桥 API 信息 ---
LB_CONFIG = {
    "app_key": "",
    "app_secret": "",
    "access_token": ""
}


def get_market_info(symbol, currency):
    """推断市场归属"""
    if symbol:
        symbol = symbol.upper()
        if symbol.endswith('.US'): return 'US'
        if symbol.endswith('.HK'): return 'HK'
        if symbol.endswith(('.CN', '.SH', '.SZ')): return 'CN'
        if symbol.endswith('.SG'): return 'SG'

    if currency == 'USD': return 'US'
    if currency == 'HKD': return 'HK'
    if currency in ['CNH', 'CNY']: return 'CN'
    if currency == 'SGD': return 'SG'
    return 'OTHER'


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/tax_report', methods=['POST'])
def get_tax_report():
    data = request.json
    start_date_str = data.get('start_date')
    end_date_str = data.get('end_date')

    if not start_date_str or not end_date_str:
        return jsonify({"status": "error", "message": "请选择日期范围"})

    try:
        start_dt = datetime.strptime(start_date_str, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date_str, "%Y-%m-%d") + timedelta(days=1) - timedelta(seconds=1)
    except ValueError:
        return jsonify({"status": "error", "message": "日期格式错误"})

    try:
        config = Config(**LB_CONFIG)
        ctx = TradeContext(config)
        flows = ctx.cash_flow(start_at=start_dt, end_at=end_dt)
    except Exception as e:
        return jsonify({"status": "error", "message": f"API连接失败: {str(e)}"})

    flow_list = []

    # --- 数据清洗与分类 ---
    for cf in flows:
        raw_time = getattr(cf, 'business_time', getattr(cf, 'transaction_time', None))
        time_str = str(raw_time) if raw_time else start_date_str

        symbol = getattr(cf, 'symbol', '')
        currency = getattr(cf, 'currency', 'USD')
        description = getattr(cf, 'description', getattr(cf, 'remark', ''))
        flow_name = str(getattr(cf, 'transaction_flow_name', 'Unknown')).upper()

        try:
            abs_amount = float(getattr(cf, 'balance', 0))
        except:
            abs_amount = 0.0

        # 正负号逻辑
        amount = abs_amount
        outcome_keywords = ['BUY', 'WITHDRAW', 'OUT', 'FEE', 'TAX', 'COMMISSION', 'DEBIT']
        income_keywords = ['SELL', 'DEPOSIT', 'IN', 'DIVIDEND', 'INTEREST', 'CREDIT']

        if any(k in flow_name for k in outcome_keywords):
            amount = -abs(abs_amount)
        elif any(k in flow_name for k in income_keywords):
            amount = abs(abs_amount)
        else:
            direction = str(getattr(cf, 'direction', '0'))
            amount = -abs(abs_amount) if direction == '1' else abs(abs_amount)

        # --- 核心分类逻辑 ---
        display_type = flow_name
        tax_category = 'ignore'  # 默认不计税
        is_pl = False

        if 'BUY' in flow_name:
            display_type = '买入'
            tax_category = 'trade_cost'
            is_pl = True
        elif 'SELL' in flow_name:
            display_type = '卖出'
            tax_category = 'trade_income'
            is_pl = True
        elif 'DIVIDEND' in flow_name:
            display_type = '股息红利'
            tax_category = 'dividend'
            is_pl = True
        elif 'INTEREST' in flow_name:
            display_type = '现金利息'
            tax_category = 'dividend'  # 利息税率同股息
            is_pl = True
        elif 'FEE' in flow_name or 'COMMISSION' in flow_name:
            display_type = '交易杂费'
            tax_category = 'trade_cost'
            is_pl = True
        elif 'TAX' in flow_name or 'WITHHOLD' in flow_name:
            display_type = '预扣税(外)'
            tax_category = 'foreign_tax'  # 这是一个特殊项，单独统计
            is_pl = True  # 算作支出，但也算作已缴税
        elif 'DEPOSIT' in flow_name:
            display_type = '入金'
        elif 'WITHDRAW' in flow_name:
            display_type = '出金'
        elif 'CONVERSION' in flow_name or 'EXCHANGE' in flow_name:
            display_type = '货币兑换'

        flow_list.append({
            "time": time_str,
            "symbol": symbol,
            "market": get_market_info(symbol, currency),
            "currency": currency,
            "type_raw": flow_name,
            "type_display": display_type,
            "description": description,
            "amount": round(amount, 2),
            "is_pl": is_pl,
            "tax_category": tax_category
        })

    # --- 聚合统计 ---
    df = pd.DataFrame(flow_list)
    result_by_market = {}
    markets = ['US', 'HK', 'CN', 'SG', 'OTHER']

    for mkt in markets:
        summary = {
            "records": [],
            "total_pl": 0.0,
            "tax_report": {
                "trade_gain": 0.0,  # 交易差价收益
                "dividend_gain": 0.0,  # 股息利息收益
                "foreign_tax": 0.0,  # 境外已扣税
                "est_china_tax": 0.0,  # 预计中国应补税
                "taxable_income": 0.0  # 应纳税所得额
            }
        }

        if not df.empty:
            mkt_df = df[df['market'] == mkt]
            summary["records"] = mkt_df.to_dict('records')

            # 1. 简单净现金流 (用于展示盈亏)
            pl_df = mkt_df[mkt_df['is_pl'] == True]
            summary["total_pl"] = round(pl_df['amount'].sum(), 2) if not pl_df.empty else 0.0

            # 2. 税务分项计算
            # 股息/利息 (全额征税)
            div_df = mkt_df[mkt_df['tax_category'] == 'dividend']
            dividend_gain = div_df['amount'].sum() if not div_df.empty else 0.0

            # 交易所得 (卖出 - 买入 - 费用 - 外国税)
            # 注意：Foreign Tax 通常是针对 Dividend 的，但也可能针对 Capital Gain。
            # 这里为了保守估计，将 Foreign Tax 单独拿出来，不直接扣减 Cost，而是最后算抵免。
            trade_income_df = mkt_df[mkt_df['tax_category'] == 'trade_income']
            trade_cost_df = mkt_df[mkt_df['tax_category'] == 'trade_cost']

            trade_gain_val = (trade_income_df['amount'].sum() if not trade_income_df.empty else 0.0) + \
                             (trade_cost_df['amount'].sum() if not trade_cost_df.empty else 0.0)

            # 境外已缴税 (作为负数存在flow里，取绝对值展示)
            tax_df = mkt_df[mkt_df['tax_category'] == 'foreign_tax']
            foreign_tax_paid = abs(tax_df['amount'].sum()) if not tax_df.empty else 0.0

            # --- 中国个税估算逻辑 (CN Tax Logic) ---
            # 规则：
            # 1. 财产转让所得 (Trade Gain): 税率20%，亏损不抵扣其他类，但年度内可互抵。如果 < 0，税额为 0。
            # 2. 利息股息红利 (Dividend): 税率20%，无扣除额。
            # 3. 抵免: 中国应纳税额 - 境外已纳税额 (若结果<0 则为0)

            taxable_trade = max(0.0, trade_gain_val)  # 亏损不交税
            taxable_dividend = dividend_gain

            china_tax_base = (taxable_trade * 0.20) + (taxable_dividend * 0.20)
            final_tax_due = max(0.0, china_tax_base - foreign_tax_paid)

            summary["tax_report"] = {
                "trade_gain": round(trade_gain_val, 2),
                "dividend_gain": round(dividend_gain, 2),
                "foreign_tax": round(foreign_tax_paid, 2),
                "est_china_tax": round(final_tax_due, 2),
                "taxable_income": round(taxable_trade + taxable_dividend, 2)
            }

        result_by_market[mkt] = summary

    return jsonify({"status": "success", "data": result_by_market})


if __name__ == '__main__':
    app.run(debug=True, port=5000)
