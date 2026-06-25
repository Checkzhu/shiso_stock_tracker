# -*- coding: utf-8 -*-
"""测试解析器"""
import sys
sys.path.insert(0, r'd:\workspace\git\ai\shiso_stock_tracker')

from app.parser import parse_report

with open(r'D:\学习\股市\A股每日选股报告_20260623.html', 'r', encoding='utf-8') as f:
    content = f.read()

result = parse_report(content, 'A股每日选股报告_20260623.html')
print('股票数量:', result['stocks_count'])
print('')
for s in result['stocks']:
    print('== %s (%s) ==' % (s['name'], s['code']))
    print('  score:', s.get('score'))
    print('  buy_price_range:', s.get('buy_price_range'))
    print('  target_price:', s.get('target_price'))
    print('  stop_loss_price:', s.get('stop_loss_price'))
    print('  holding_period:', s.get('holding_period'))
    print('  expected_return:', s.get('expected_return'))
    print('  risks_count:', len(s.get('risks') or []))
    print('  chain_flow_count:', len(s.get('chain_flow') or []))
    depth = s.get('depth_analysis') or {}
    print('  depth keys:', list(depth.keys()))
    print('    industry_tech:', bool(depth.get('industry_tech')))
    print('    rise_reasons keys:', list((depth.get('rise_reasons') or {}).keys()))
    print('    physics_limits:', bool(depth.get('physics_limits')))
    print('    substitution_threat:', bool(depth.get('substitution_threat')))
    print('    supply_demand_logic:', bool(depth.get('supply_demand_logic')))
    print('    geo_risk:', bool(depth.get('geo_risk')))
    print('    capacity_feasibility:', bool(depth.get('capacity_feasibility')))
    print('    feasibility_assessment:', bool(depth.get('feasibility_assessment')))
    print('    demand_sustainability:', bool(depth.get('demand_sustainability')))
    print('    valuation_rationality:', bool(depth.get('valuation_rationality')))
    print('    irreplaceability:', bool(depth.get('irreplaceability')))
    print('')
