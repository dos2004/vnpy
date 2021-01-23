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
        "price_offset": 0.05,
        "price_offset_max": 0.1,
        "volume": 2,
        "max_volume_ratio": 0,
        "interval": 3,
        "min_order_level": 1,
        "min_order_volume": 0,
        "sell_max_volume": 0,
        "buy_max_volume": 0,
        "auto_trade_volume": 310,
        "sell_max_ratio": 1,
        "buy_max_ratio": 1,
        "reward_ratio": 0.01,
        "min_pos": 50000,
        "max_pos": 50000,
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
        self.price_offset_max   = setting["price_offset_max"]
        self.volume             = setting["volume"]
        self.max_volume_ratio   = setting.get("max_volume_ratio", 0)
        assert 0 <= self.max_volume_ratio <= 1
        self.interval           = setting["interval"]
        self.min_order_level    = setting["min_order_level"]
        self.min_order_volume   = setting["min_order_volume"]
        self.sell_max_volume    = setting["sell_max_volume"]
        self.buy_max_volume     = setting["buy_max_volume"]
        self.auto_trade_volume  = setting["auto_trade_volume"]
        self.sell_max_ratio     = setting["sell_max_ratio"]
        self.buy_max_ratio      = setting["buy_max_ratio"]
        self.reward_ratio       = setting["reward_ratio"]
        self.min_pos            = setting["min_pos"]
        self.max_pos            = setting["max_pos"]
        self.enable_ioc         = setting.get("enable_ioc", False)
        self.ioc_intervel       = setting.get("ioc_interval", self.interval)

        # validate setting
        assert self.price_offset <= self.price_offset_max
        assert 0 <= self.min_order_level <= 5

        # Variables
        self.pos = 0
        self.timer_count = 0
        self.vt_ask_orderid = ""
        self.vt_ask_price = 0.0
        self.vt_bid_orderid = ""
        self.vt_bid_price = 0.0
        self.origin_ask_price = 0.00000002
        self.origin_bid_price = 0.00000001
        self.last_ask_price = 0.00000002
        self.last_bid_price = 0.00000001
        self.last_ask_volume = 0.0
        self.last_bid_volume = 0.0
        self.total_ask_volume = 0.0
        self.total_bid_volume = 0.0
        self.ask_order_level = 0
        self.bid_order_level = 0

        self.last_tick = None
        self._init_market_accounts(self.vt_symbol)

        self.subscribe(self.vt_symbol)
        self.put_parameters_event()
        self.put_variables_event()

    def _init_market_accounts(self, active_vt_symbol):
        SYMBOL_SPLITTER = re.compile(r"^(\w+)[-:/]?(BTC|ETH|BNB|XRP|USDT|USDC|USDS|TUSD|PAX|DAI)$")
        market_token_pair = active_vt_symbol.split('.')[0]
        active_market = active_vt_symbol.split('.')[1]
        if not market_token_pair or not active_market:
            self.algo_engine.main_engine.write_log(f"ERROR: parse active_vt {active_vt_symbol} failed")
            return False

        token_pair_match = SYMBOL_SPLITTER.match(market_token_pair.upper())
        if not token_pair_match:
            self.algo_engine.main_engine.write_log(f"ERROR: parse symbol {market_token_pair} failed")
            return False

        self.market_vt_tokens = [
            f"{active_market}.{token_pair_match.group(1)}",
            f"{active_market}.{token_pair_match.group(2)}"
        ]
        self.current_balance = {}
        self._update_current_balance()

    def _update_current_balance(self):
        for vt_token in self.market_vt_tokens:
            user_account = self.algo_engine.main_engine.get_account(vt_token)
            if type(user_account) is not AccountData:
                return False
            self.current_balance[vt_token] = user_account.balance
        return True

    def on_start(self):
        """"""
        random.seed(time.time())
        self.write_log(f"开始流动性挖矿: {self.price_offset}, {self.price_offset_max}, {self.volume}, {self.interval}, {self.min_order_level}, {self.min_order_volume}, {self.sell_max_volume}, {self.buy_max_volume}, {self.auto_trade_volume}")
        self.pricetick = self.algo_engine.main_engine.get_contract(self.vt_symbol).pricetick
        self.volumetick = self.algo_engine.main_engine.get_contract(self.vt_symbol).min_volume
        assert self.pricetick > 0

    def on_tick(self, tick: TickData):
        """"""
        self.last_tick = tick

        market_price = (tick.ask_price_1 + tick.bid_price_1) / 2
        if self.vt_ask_orderid != "":
            self.ask_order_alive_tick += 1
            # if time to kill
            cancel_ask = False
            if self.enable_ioc and self.ask_order_alive_tick > self.ioc_intervel:
                self.write_log(f"卖单{self.vt_ask_orderid}有效时间{self.ask_order_alive_tick} ticks > {self.ioc_intervel},取消")
                cancel_ask = True
            if not cancel_ask:
                total_ask_volume = 0
                for num_level in range(1, 6):
                    ask_price = getattr(tick, f"ask_price_{num_level}")
                    if 0 < ask_price < self.last_ask_price:
                        total_ask_volume += getattr(tick, f"ask_volume_{num_level}")
                # min_ask_price = getattr(tick, f"ask_price_{self.ask_order_level}") if self.ask_order_level > 0 else market_price
                # vt_ask_price = round_to(min_ask_price + self.pricetick, self.pricetick)
                vt_ask_price = getattr(tick, f"ask_price_1")
                if self.vt_ask_price < vt_ask_price:
                    cancel_ask = True
                    self.write_log(f"当前卖单{self.vt_ask_price} 低于最新卖{self.ask_order_level}价 {vt_ask_price}，取消")
                elif self.vt_ask_price > vt_ask_price:
                    cancel_ask = True
                    self.write_log(f"当前卖单{self.vt_ask_price} 高于最新卖{self.ask_order_level}价 {vt_ask_price}，取消")
                elif abs(self.total_ask_volume - total_ask_volume) > (self.total_ask_volume / 2):
                    cancel_ask = True
                    self.write_log(f"---> 当前卖单{self.vt_ask_price} 取消，因为之前的订单量发生了变化")
            if cancel_ask:
                self.cancel_order(self.vt_ask_orderid)
                # self.ask_order_alive_tick = 0

        if self.vt_bid_orderid != "":
            self.bid_order_alive_tick += 1
            # if time to kill
            cancel_bid = False
            if self.enable_ioc and self.bid_order_alive_tick > self.ioc_intervel:
                self.write_log(f"买单{self.vt_bid_orderid}有效时间{self.bid_order_alive_tick} ticks > {self.ioc_intervel},取消")
                cancel_bid = True
            if not cancel_bid:
                total_bid_volume = 0
                for num_level in range(1, 6):
                    bid_price = getattr(tick, f"bid_price_{num_level}")
                    if bid_price > self.last_bid_price:
                        total_bid_volume += getattr(tick, f"bid_volume_{num_level}")
                # max_bid_price = getattr(tick, f"bid_price_{self.bid_order_level}") if self.bid_order_level > 0 else market_price
                # vt_bid_price = round_to(max_bid_price - self.pricetick, self.pricetick)
                vt_bid_price = getattr(tick, f"bid_price_1")
                if self.vt_bid_price > vt_bid_price:
                    cancel_bid = True
                    self.write_log(f"当前买单{self.vt_bid_price} 高于最新买{self.bid_order_level}价 {vt_bid_price}，取消")
                elif self.vt_bid_price < vt_bid_price:
                    cancel_bid = True
                    self.write_log(f"当前买单{self.vt_bid_price} 低于最新买{self.bid_order_level}价 {vt_bid_price}，取消")
                elif abs(self.total_bid_volume - total_bid_volume) > (self.total_bid_volume / 2):
                    cancel_bid = True
                    self.write_log(f"---> 当前买单{self.vt_bid_price} 取消，因为之前的订单量发生了变化")
            if cancel_bid:
                self.cancel_order(self.vt_bid_orderid)
                # self.bid_order_alive_tick = 0

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
        self.write_log(f"当前余额 {self.current_balance}, 持仓 {self.pos}")

        if not self._update_current_balance():
            self.write_log(f"查询余额失败，上次余额: [{self.current_balance}]")
            return

        use_max_volume = self.max_volume_ratio > 0
        max_volume_ratio = self.max_volume_ratio
        market_price = (self.last_tick.ask_price_1 + self.last_tick.bid_price_1) / 2
        if self.vt_ask_orderid == "":
            self.ask_order_level = 0
            for num_level in range(self.min_order_level, 0, -1):
                ask_price = getattr(self.last_tick, f"ask_price_{num_level}")
                if 0 < ask_price < market_price * (1 + self.reward_ratio * 0.99):
                    self.ask_order_level = num_level
                    break
            if self.ask_order_level > 0:
                total_ask_volume = 0
                for num_level in range(1, self.ask_order_level + 1):
                    total_ask_volume += getattr(self.last_tick, f"ask_volume_{num_level}")
                if total_ask_volume != self.last_ask_volume:
                    one_ask_price = getattr(self.last_tick, f"ask_price_1")
                    one_ask_volume = getattr(self.last_tick, f"ask_volume_1")
                    min_ask_price = getattr(self.last_tick, f"ask_price_{self.ask_order_level}") if self.ask_order_level > 0 else market_price
                    vt_ask_price = round_to(min_ask_price + self.pricetick, self.pricetick)
                    if self.origin_ask_price == 0.00000002:
                        self.origin_ask_price = vt_ask_price
                    ask_condition0 = self.last_ask_price == 0.00000002
                    ask_condition1 = (self.last_ask_price * (1 - self.price_offset)) < vt_ask_price < (self.last_ask_price * (1 + self.price_offset))
                    ask_condition2 = vt_ask_price > (self.origin_ask_price * (1 - self.price_offset_max))
                    ask_condition8 = one_ask_price < (self.origin_ask_price * (1 - self.price_offset_max * 2))
                    self.write_log(f"---> 流动性挖矿卖出condition1: {ask_condition1}, condition2: {ask_condition2}")
                    if ask_condition0 or (ask_condition1 and ask_condition2):
                        self.last_ask_price = vt_ask_price
                        self.vt_ask_price = one_ask_price
                        self.total_ask_volume = total_ask_volume
                        max_volume = self.current_balance[self.market_vt_tokens[0]] * self.sell_max_ratio
                        if 0 < self.sell_max_volume < max_volume:
                            max_volume = self.sell_max_volume
                        min_volume = self.volume * total_ask_volume
                        if self.min_order_volume > 0 and min_volume < self.min_order_volume:
                            min_volume = self.min_order_volume
                        volume = min_volume if not use_max_volume else max_volume * max_volume_ratio
                        if volume >= max_volume:
                            volume = max_volume
                        self.last_ask_volume = round_to(volume - self.volumetick, self.volumetick)
                        self.write_log(f"流动性挖矿卖出价格: {vt_ask_price}, 量: {self.last_ask_volume}")
                        self.vt_ask_orderid = self.sell(self.vt_symbol, vt_ask_price, self.last_ask_volume)
                        self.ask_order_alive_tick = 0
                    elif ask_condition8 and one_ask_volume < self.auto_trade_volume:
                        self.write_log(f"---> 流动性挖矿买入低价one_ask_price: {one_ask_price}, one_ask_volume: {one_ask_volume}")
                        self.buy(self.vt_symbol, one_ask_price, one_ask_volume)
                else:
                    self.write_log(f"---> 流动性挖矿卖出下单失败，因为卖单总数量等于上一单数量")
            else:
                self.write_log(f"---> 流动性挖矿卖出下单失败，因为没有合适的下单位置")

        if self.vt_bid_orderid == "":
            self.bid_order_level = 0
            for num_level in range(self.min_order_level, 0, -1):
                bid_price = getattr(self.last_tick, f"bid_price_{num_level}")
                if bid_price > market_price * (1 - self.reward_ratio * 0.99):
                    self.bid_order_level = num_level
                    break
            if self.bid_order_level > 0:
                total_bid_volume = 0
                for num_level in range(1, self.bid_order_level + 1):
                    total_bid_volume += getattr(self.last_tick, f"bid_volume_{num_level}")
                if total_bid_volume != self.last_bid_volume:
                    one_bid_price = getattr(self.last_tick, f"bid_price_1")
                    one_bid_volume = getattr(self.last_tick, f"bid_volume_1")
                    max_bid_price = getattr(self.last_tick, f"bid_price_{self.bid_order_level}") if self.bid_order_level > 0 else market_price
                    vt_bid_price = round_to(max_bid_price - self.pricetick, self.pricetick)
                    if self.origin_bid_price == 0.00000001:
                        self.origin_bid_price = vt_bid_price
                    bid_condition0 = self.last_bid_price == 0.00000001
                    bid_condition1 = (self.last_bid_price * (1 - self.price_offset)) < vt_bid_price < (self.last_bid_price * (1 + self.price_offset))
                    bid_condition2 = vt_bid_price < (self.origin_bid_price * (1 + self.price_offset_max))
                    bid_condition8 = one_bid_price > (self.origin_bid_price * (1 + self.price_offset_max * 2))
                    self.write_log(f"---> 流动性挖矿买入condition1: {bid_condition1}, condition2: {bid_condition2}")
                    if bid_condition0 or (bid_condition1 and bid_condition2):
                        self.last_bid_price = vt_bid_price
                        self.vt_bid_price = one_bid_price
                        self.total_bid_volume = total_bid_volume
                        max_volume = self.current_balance[self.market_vt_tokens[1]] * self.buy_max_ratio / vt_bid_price
                        if 0 < self.buy_max_volume < max_volume:
                            max_volume = self.buy_max_volume
                        min_volume = self.volume * total_bid_volume
                        if self.min_order_volume > 0 and min_volume < self.min_order_volume:
                            min_volume = self.min_order_volume
                        volume = min_volume if not use_max_volume else max_volume * max_volume_ratio
                        if volume >= max_volume:
                            volume = max_volume
                        self.last_bid_volume = round_to(volume - self.volumetick, self.volumetick)
                        self.write_log(f"流动性挖矿买入价格: {vt_bid_price}, 量: {self.last_bid_volume}")
                        self.vt_bid_orderid = self.buy(self.vt_symbol, vt_bid_price, self.last_bid_volume)
                        self.bid_order_alive_tick = 0
                    elif bid_condition8 and one_bid_volume < self.auto_trade_volume:
                        self.write_log(f"---> 流动性挖矿卖出高价one_bid_price: {one_bid_price}, one_bid_volume: {one_bid_volume}")
                        self.sell(self.vt_symbol, one_bid_price, one_bid_volume)
                else:
                    self.write_log(f"---> 流动性挖矿买入下单失败，因为买单总数量等于上一单数量")
            else:
                self.write_log(f"---> 流动性挖矿买入下单失败，因为没有合适的下单位置")
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
        if trade.direction == Direction.SHORT:
            self.write_log(f"流动性挖矿卖单{trade.vt_orderid}成交，价:{trade.price}, 量:{trade.volume}")
            self.pos -= trade.volume
        elif trade.direction == Direction.LONG:
            self.write_log(f"流动性挖矿买单{trade.vt_orderid}成交，价:{trade.price}, 量:{trade.volume}")
            self.pos += trade.volume

        self.put_variables_event()

    def on_stop(self):
        """"""
        self.write_log("停止 流动性挖矿")
        # self.write_log(f"账户状态:{self.algo_engine.main_engine.get_all_accounts()}")
        time.sleep(5)
