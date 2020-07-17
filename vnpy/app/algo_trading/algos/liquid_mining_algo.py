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


class LiquidMiningAlgo(AlgoTemplate):
    """"""
    display_name = "交易所 流动性挖坑"

    default_setting = {
        "vt_symbol": "",
        "price_offset": 0.0,
        "price_tolerance": 0.0,
        "volume": 0,
        "interval": 10,
        "min_order_level": 5,
        "min_pos": 5000,
        "max_pos": 10000,
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
        self.price_offset       = setting["price_offset"]
        self.price_tolerance    = setting["price_tolerance"]
        self.volume             = setting["volume"]
        self.interval           = setting["interval"]
        self.min_order_level    = setting["min_order_level"]
        self.min_pos            = setting["min_pos"]
        self.max_pos            = setting["max_pos"]

        # validate setting
        assert self.price_tolerance <= self.price_offset
        assert 0 <= self.min_order_level <= 5

        # Variables
        self.pos = 0
        self.timer_count = 0
        self.vt_ask_orderid = ""
        self.vt_ask_price = 0.0
        self.vt_bid_orderid = ""
        self.vt_bid_price = 0.0

        self.last_tick = None

        self.subscribe(self.vt_symbol)
        self.put_parameters_event()
        self.put_variables_event()

    def on_start(self):
        """"""
        random.seed(time.time())
        self.write_log("开始 流动性挖矿")
        self.pricetick = self.algo_engine.main_engine.get_contract(self.vt_symbol).pricetick
        assert self.pricetick > 0

    def on_tick(self, tick: TickData):
        """"""
        self.last_tick = tick

        price_tolerance = self.price_tolerance
        market_price = (tick.ask_price_1 + tick.bid_price_1) / 2

        if self.vt_ask_orderid != "":
            cancel_ask = False
            min_ask_price = getattr(tick, f"ask_price_{self.min_order_level}") if self.min_order_level > 0 else market_price
            target_ask_price = round_to(market_price * ((100 + self.price_offset)/100), self.pricetick)
            ask_price_diff = 100 * abs(self.vt_ask_price - target_ask_price) / target_ask_price
            if ask_price_diff > price_tolerance:
                cancel_ask = True
                self.write_log(f"当前卖单{self.vt_ask_price} 超出目标价 {target_ask_price} {ask_price_diff:.3f}%，取消")
            if self.vt_ask_price < min_ask_price:
                cancel_ask = True
                self.write_log(f"当前卖单{self.vt_ask_price} 低于最低卖{self.min_order_level}价 {min_ask_price:.3f}，取消")
            if cancel_ask:
                self.cancel_order(self.vt_ask_orderid)

        if self.vt_bid_orderid != "":
            cancel_bid = False
            max_bid_price = getattr(tick, f"bid_price_{self.min_order_level}") if self.min_order_level > 0 else market_price
            target_bid_price = round_to(market_price * ((100 - self.price_offset)/100), self.pricetick)
            bid_price_diff = 100 * abs(self.vt_bid_price - target_bid_price) / target_bid_price
            if bid_price_diff > price_tolerance:
                cancel_bid = True
                self.write_log(f"当前买单{self.vt_bid_price} 超出目标价 {target_bid_price} {bid_price_diff:.3f}%，取消")
            if self.vt_bid_price > max_bid_price:
                cancel_bid = True
                self.write_log(f"当前买单{self.vt_bid_price} 高于最高买{self.min_order_level}价 {max_bid_price:.3f}，取消")
            if cancel_bid:
                self.cancel_order(self.vt_bid_orderid)

    def on_timer(self):
        """"""
        if not self.last_tick:
            return

        if self.pos < self.min_pos or self.pos > self.max_pos:
            self.cancel_all()
            self.write_log(f"当前持仓: {self.pos} 超出[{self.min_pos}, {self.max_pos}]范围，停止流动性挖矿")
            return

        self.timer_count += 1
        if self.timer_count < self.interval:
            self.put_variables_event()
            return
        self.timer_count = 0

        market_price = (self.last_tick.ask_price_1 + self.last_tick.bid_price_1) / 2
        if self.vt_ask_orderid == "":
            min_ask_price = getattr(self.last_tick, f"ask_price_{self.min_order_level}") if self.min_order_level > 0 else market_price
            vt_ask_price = round_to(market_price * ((100 + self.price_offset)/100), self.pricetick)
            if vt_ask_price >= min_ask_price:
                self.vt_ask_price = vt_ask_price
                self.write_log(f"委托流动性挖矿卖单，价格：{self.vt_ask_price}")
                self.vt_ask_orderid = self.sell(self.vt_symbol, self.vt_ask_price, self.volume)

        if self.vt_bid_orderid == "":
            max_bid_price = getattr(self.last_tick, f"bid_price_{self.min_order_level}") if self.min_order_level > 0 else market_price
            vt_bid_price = round_to(market_price * ((100 - self.price_offset)/100), self.pricetick)
            if vt_bid_price <= max_bid_price:
                self.vt_bid_price = vt_bid_price
                self.write_log(f"委托流动性挖矿买单，价格：{self.vt_bid_price}")
                self.vt_bid_orderid = self.buy(self.vt_symbol, self.vt_bid_price, self.volume)
        self.put_variables_event()

    def on_order(self, order: OrderData):
        """"""
        if order.vt_orderid == self.vt_ask_orderid:
            if not order.is_active():
                self.vt_ask_orderid = ""
                self.vt_ask_price = 0.0
        elif order.vt_orderid == self.vt_bid_orderid:
            if not order.is_active():
                self.vt_bid_orderid = ""
                self.vt_bid_price = 0.0
        self.put_variables_event()

    def on_trade(self, trade: TradeData):
        """"""
        if trade.tradeid == self.vt_ask_orderid:
            self.pos -= trade.volume
        elif trade.tradeid == self.vt_bid_orderid:
            self.pos += trade.volume

        self.put_variables_event()

    def on_stop(self):
        """"""
        self.write_log("停止 流动性挖矿")
        # self.write_log(f"账户状态:{self.algo_engine.main_engine.get_all_accounts()}")
        time.sleep(5)
