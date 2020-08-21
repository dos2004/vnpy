from collections import defaultdict
from decimal import Decimal
from _datetime import datetime, timedelta
from enum import Enum
import math
import random
import re
import requests
import time

from vnpy.app.algo_trading import AlgoTemplate
from vnpy.trader.utility import round_to
from vnpy.trader.constant import Direction, Status, OrderType
from vnpy.trader.object import AccountData, OrderData, TradeData, TickData
from vnpy.trader.engine import BaseEngine


class AutoMarketMakerAlgo(AlgoTemplate):
    """"""
    display_name = "交易所稳定币对 流动性挖坑"

    default_setting = {
        "vt_symbol": "",
        "base_asset": 0.0,
        "quote_asset": 0.0,
        "price_offset": 1,
        "price_tolerance": 5,
        "interval": 10,
        "volume": 1000,
        "min_order_level": 5,
        "max_loss": 10
    }

    variables = [
        "pos",
        "timer_count",
        "vt_ask_orderid",
        "vt_bid_orderid"
    ]

    def __init__(
        self,
        algo_engine: BaseEngine,
        algo_name: str,
        setting: dict
    ):
        """"""
        super().__init__(algo_engine, algo_name, setting)

        # Parameters
        self.vt_symbol          = setting["vt_symbol"]
        self.base_asset         = setting["base_asset"]
        self.quote_asset        = setting["quote_asset"]
        assert self.base_asset != 0 and self.quote_asset != 0
        self.x = self.base_asset
        self.y = self.quote_asset

        self.price_offset       = setting["price_offset"]
        self.price_tolerance    = setting["price_tolerance"]
        self.interval           = setting["interval"]
        self.volume             = setting["volume"]
        self.min_order_level    = setting["min_order_level"]
        self.max_loss           = setting.get("max_loss", 0.1 * (self.base_asset + self.quote_asset))
        self.fee_rate           = setting.get("fee_rate", 0.0015)
        assert 0 <= self.fee_rate < 1

        # validate setting
        assert 0 <= self.min_order_level <= 5

        # Variables
        self.pos = 0
        self.timer_count = 0
        self.vt_ask_orderid = ""
        self.vt_ask_price = 0.0
        self.vt_bid_orderid = ""
        self.vt_bid_price = 0.0

        self.hedge_ask_orderids = []
        self.hedge_bid_orderids = []

        self.last_tick = None
        self.stopped = True

        self.subscribe(self.vt_symbol)
        self.put_parameters_event()
        self.put_variables_event()

    def on_start(self):
        """"""
        random.seed(time.time())
        self.write_log("开始 自动做市")
        self.stopped = False
        self.pricetick = self.algo_engine.main_engine.get_contract(self.vt_symbol).pricetick if self.algo_engine.main_engine is not None else 0.00000001
        
        assert self.pricetick > 0

    def on_tick(self, tick: TickData):
        """"""
        self.last_tick = tick
        self.prune_ask_orders(tick)
        self.prune_bid_orders(tick)
    
    def prune_ask_orders(self, tick: TickData):
        #TODO: prune hedge orders
        market_price = (tick.ask_price_1 + tick.bid_price_1) / 2
        if self.vt_ask_orderid != "":
            target_ask_price = round_to(market_price * ((100 + self.price_offset)/100), self.pricetick)
            if self.vt_ask_price > target_ask_price:
                self.write_log(f"当前卖单{self.vt_ask_price} 超出目标价 {target_ask_price}，取消{self.vt_ask_orderid}")
                self.cancel_order(self.vt_ask_orderid)

    def prune_bid_orders(self, tick: TickData):
        #TODO: prune hedge orders
        market_price = (tick.ask_price_1 + tick.bid_price_1) / 2
        if self.vt_bid_orderid != "":
            target_bid_price = round_to(market_price * ((100 - self.price_offset)/100), self.pricetick)
            if  self.vt_bid_price < target_bid_price:
                self.write_log(f"当前买单{self.vt_bid_price} 超出目标价 {target_bid_price}，取消{self.vt_bid_orderid}")
                self.cancel_order(self.vt_bid_orderid)

    def on_timer(self):
        """"""
        if not self.last_tick or self.stopped:
            return

        if not self.check_assets_balance():
            self.cancel_all()
            self.stopped = True
            return

        self.timer_count += 1
        if self.timer_count < self.interval:
            self.put_variables_event()
            return
        self.timer_count = 0

        market_price = (self.last_tick.ask_price_1 + self.last_tick.bid_price_1) / 2
        if self.vt_ask_orderid == "" and len(self.hedge_ask_orderids) == 0:
            min_ask_price = getattr(self.last_tick, f"ask_price_{self.min_order_level}") if self.min_order_level > 0 else market_price
            vt_ask_price = round_to(market_price * ((100 + self.price_offset)/100), self.pricetick)
            if vt_ask_price >= min_ask_price and math.fabs(vt_ask_price - 1)*100 <= self.price_tolerance:
                self.vt_ask_price = vt_ask_price
                self.vt_ask_volume = self.volume
                if self.vt_ask_volume > 0:
                    self.write_log(f"委托AMM卖单，价格:{self.vt_ask_price}, 下单量: {self.vt_ask_volume}")
                    self.vt_ask_orderid = self.sell(self.vt_symbol, self.vt_ask_price, self.vt_ask_volume)

        if self.vt_bid_orderid == "" and len(self.hedge_bid_orderids) == 0:
            max_bid_price = getattr(self.last_tick, f"bid_price_{self.min_order_level}") if self.min_order_level > 0 else market_price
            vt_bid_price = round_to(market_price * ((100 - self.price_offset)/100), self.pricetick)
            if vt_bid_price <= max_bid_price and math.fabs(vt_bid_price - 1)*100 <= self.price_tolerance:
                self.vt_bid_price = vt_bid_price
                self.vt_bid_volume = self.volume
                if self.vt_bid_volume > 0:
                    self.write_log(f"委托AMM买单，价格:{self.vt_bid_price}，下单量: {self.vt_bid_volume}")
                    self.vt_bid_orderid = self.buy(self.vt_symbol, self.vt_bid_price, self.vt_bid_volume)

        #self.write_log(f"{self.vt_ask_orderid}, {self.vt_bid_orderid}")
        self.put_variables_event()

    def on_order(self, order: OrderData):
        """"""
        if order.vt_orderid == self.vt_ask_orderid:
            if not order.is_active():
                if order.traded > 0:
                    self.write_log(f"AMM卖单成交，价格:{order.price}，成交量: {order.traded}")
                    self.hedge(order)
                self.vt_ask_orderid = ""
                self.vt_ask_price = 0.0
                self.x-=order.traded
                self.y+=order.traded*order.price
        elif order.vt_orderid == self.vt_bid_orderid:
            if not order.is_active():
                if order.traded > 0:
                    self.write_log(f"AMM买单成交，价格:{order.price}，成交量: {order.traded}")
                    self.hedge(order)
                self.vt_bid_orderid = ""
                self.vt_bid_price = 0.0
                self.x+=order.traded
                self.y-=order.traded*order.price
        elif order.vt_orderid in self.hedge_ask_orderids:
            if not order.is_active():
                self.write_log(f"对冲卖单成交，价格:{order.price}，成交量: {order.traded}")
                self.hedge_ask_orderids.remove(order.vt_orderid)
                self.x-=order.traded
                self.y+=order.traded*order.price
        elif order.vt_orderid in self.hedge_bid_orderids:
            if not order.is_active():
                self.write_log(f"对冲买单成交，价格:{order.price}，成交量: {order.traded}")
                self.hedge_bid_orderids.remove(order.vt_orderid)
                self.x+=order.traded
                self.y-=order.traded*order.price
        self.put_variables_event()

    def on_trade(self, trade: TradeData):
        """"""
        self.put_variables_event()

    def hedge(self, order: OrderData):
        """"""
        volume = order.traded
        if order.direction == Direction.SHORT:
            hedge_price = round_to(order.price * (1-self.fee_rate), self.pricetick)
            volume = volume/(1-self.fee_rate)
            vt_hedge_bid_orderid = self.buy(
                self.vt_symbol,
                hedge_price,
                volume
            )
            if vt_hedge_bid_orderid != "":
                self.write_log(f"委托AMM对冲买单，价格:{order.price}, 下单量: {volume}")
                self.hedge_bid_orderids.append(vt_hedge_bid_orderid)
        elif order.direction == Direction.LONG:
            hedge_price = round_to(order.price / (1-self.fee_rate), self.pricetick)
            vt_hedge_ask_orderid = self.sell(
                self.vt_symbol,
                hedge_price,
                volume
            )
            if vt_hedge_ask_orderid != "":
                self.write_log(f"委托AMM对冲卖单，价格:{order.price}, 下单量: {volume}")
                self.hedge_ask_orderids.append(vt_hedge_ask_orderid)

    def on_stop(self):
        """"""
        self.write_log("停止 流动性挖矿")
        # self.write_log(f"账户状态:{self.algo_engine.main_engine.get_all_accounts()}")
        time.sleep(5)

    def check_assets_balance(self):
        """"""
        x, y = self.x, self.y
        if x < 0 or y < 0:
            self.write_log(f"当前持仓: {x}*{y} < 0 ，停止自动做市机器人")
            self.stopped = True

        if (x + y) - (self.base_asset + self.quote_asset) < -self.max_loss:
            self.write_log(f"当前持仓: {x}+{y} < {self.base_asset+self.quote_asset} - {self.max_loss} ，停止自动做市机器人")
            return False
        
        return True
