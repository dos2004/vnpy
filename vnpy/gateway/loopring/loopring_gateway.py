"""
Gateway for Loopring Crypto Exchange.
"""

from copy import copy
from datetime import datetime, timedelta
from enum import Enum
import hashlib
import hmac
from operator import itemgetter
from random import randint
import re
import sys
import time
from threading import Lock
from time import sleep
from typing import Any, Sequence
import ujson
import urllib

from vnpy.api.rest import RestClient, Request
from vnpy.api.websocket import WebsocketClient
from vnpy.trader.constant import (
    Direction,
    Exchange,
    Product,
    Status,
    OrderType,
    Interval
)
from vnpy.trader.gateway import BaseGateway
from vnpy.trader.object import (
    TickData,
    OrderData,
    TradeData,
    AccountData,
    ContractData,
    BarData,
    OrderRequest,
    CancelRequest,
    SubscribeRequest,
    HistoryRequest
)
from vnpy.trader.event import EVENT_TIMER
from vnpy.event import Event

from .ethsnarks.eddsa import PureEdDSA
from .ethsnarks.eddsa import PoseidonEdDSA
from .ethsnarks.field import FQ, SNARK_SCALAR_FIELD
from .ethsnarks.poseidon import poseidon_params, poseidon
from .loopring_orderId_manager import BaseOrderIdManager


REST_HOST = "https://api.loopring.io"
WEBSOCKET_TRADE_HOST = "wss://ws.loopring.io/v2/ws"
WEBSOCKET_DATA_HOST =  "wss://ws.loopring.io/v2/ws"

STATUS_LOOPRING2VT = {
    "processing": Status.NOTTRADED,
    "filled"    : Status.PARTTRADED,
    "processed" : Status.ALLTRADED,
    "cancelled" : Status.CANCELLED
}

ORDERTYPE_VT2LOOPRING = {
    OrderType.LIMIT: "LIMIT",
    OrderType.MARKET: "MARKET"
}
ORDERTYPE_LOOPRING2VT = {v: k for k, v in ORDERTYPE_VT2LOOPRING.items()}

DIRECTION_VT2LOOPRING = {
    Direction.LONG: "BUY",
    Direction.SHORT: "SELL"
}
DIRECTION_LOOPRING2VT = {v: k for k, v in DIRECTION_VT2LOOPRING.items()}

INTERVAL_VT2LOOPRING = {
    Interval.MINUTE: "1m",
    Interval.HOUR: "1h",
    Interval.DAILY: "1d",
}

TIMEDELTA_MAP = {
    Interval.MINUTE: timedelta(minutes=1),
    Interval.HOUR: timedelta(hours=1),
    Interval.DAILY: timedelta(days=1),
}


class Security(Enum):
    NONE = 0
    SIGNED = 1
    API_KEY = 2


symbol_name_map = {}

class LoopringGateway(BaseGateway):
    """
    VN Trader Gateway for Loopring connection.
    """

    default_setting = {
        "key": "",
        "secret": "",
        "session_number": 3,
        "proxy_host": "",
        "proxy_port": 0,
        "address": "",
    }

    exchanges = [Exchange.LOOPRING]

    MAX_ORDER_ID = 1_000_000

    def __init__(self, event_engine):
        """Constructor"""
        super().__init__(event_engine, "LOOPRING")

        self.subscribe_reqs = {}

        self.orders = {}

        # Max subcribe ws can be up to 3 for triangle algo
        self.trade_ws_apis = [LoopringTradeWebsocketApi(self)]
        self.market_ws_apis = [LoopringDataWebsocketApi(self)]
        self.rest_api = LoopringRestApi(self)

        # self.event_engine.register(EVENT_TIMER, self.process_timer_event)

    def connect(self, setting: dict):
        """"""
        key = setting["key"]
        secret = setting["secret"]
        session_number = setting["session_number"]
        proxy_host = setting["proxy_host"]
        proxy_port = setting["proxy_port"]
        address = setting["address"]
        accountId = setting["accountId"]
        exchangeId = setting.get("exchangeId", 1)

        self.rest_api.connect(exchangeId, key, secret, session_number,
                              proxy_host, proxy_port, address, accountId)
        for market_ws_api in self.market_ws_apis:
            market_ws_api.connect(proxy_host, proxy_port)
        for trace_ws_api in self.trade_ws_apis:
            trace_ws_api.connect(WEBSOCKET_DATA_HOST, proxy_host, proxy_port)

    def subscribe(self, req: SubscribeRequest):
        """"""
        self.write_log(f"loopring gateway subscribe {req}")
        if req.symbol in self.subscribe_reqs:
            self.write_log(f"ERROR: already subscribed {len(self.subscribe_reqs)} sources {self.subscribe_reqs}")
            return

        self.trade_ws_apis[0].subscribe(req)
        self.market_ws_apis[0].subscribe(req)
        self.subscribe_reqs[req.symbol] = req

    def send_order(self, req: OrderRequest):
        """"""
        return self.rest_api.send_order(req)

    def cancel_order(self, req: CancelRequest):
        """"""
        self.rest_api.cancel_order(req)

    def query_account(self):
        """"""
        pass

    def query_position(self):
        """"""
        pass

    def query_history(self, req: HistoryRequest):
        """"""
        return self.rest_api.query_history(req)

    def close(self):
        """"""
        self.rest_api.stop()
        for ws_api in self.trade_ws_apis:
            ws_api.stop()
        for ws_api in self.market_ws_apis:
            ws_api.stop()

    def on_order(self, order: OrderData):
        """"""
        if order.is_active():
            self.orders[order.orderid] = order
        else:
            self.orders.pop(order.orderid)
        super().on_order(order)

    def process_timer_event(self, event: Event):
        """"""
        #TODO: handle timeout


class LoopringRestApi(RestClient):
    """
    LOOPRING REST API
    """

    def __init__(self, gateway: LoopringGateway):
        """"""
        super().__init__()

        self.gateway = gateway
        self.gateway_name = gateway.gateway_name

        self.trade_ws_apis = self.gateway.trade_ws_apis

        self.key = ""
        self.secret = ""

        self.user_stream_key = ""
        self.keep_alive_count = 0
        self.recv_window = 5000
        self.time_offset = 0

        self.order_count = 0
        self.orderId_limit = self.gateway.MAX_ORDER_ID
        self.order_count_lock = Lock()
        self.connect_time = 0

        self.address = ""
        self.publicKeyX = ""
        self.publicKeyY = ""
        self.lrcTokenId = 2
        self.ethTokenId = 0
        self.accountId = 0

        self.failed_orderId = {} # {tokenSId:[reused orderId list]}
        self.contracts = {}
        self.tokens = {}

        self.orderId_manager = BaseOrderIdManager()


    def _order_params(self, request):
        """
        Convert params based on https://developers.infogr.am/rest/request-signing.html
        """
        method = request.method
        url = urllib.parse.quote(REST_HOST + request.path, safe='')
        data = urllib.parse.quote("&".join([f"{k}={urllib.parse.quote(str(v), safe='')}" for k, v in request.params.items()]), safe='')
        return "&".join([method, url, data])

    def sign(self, request):
        """
        Generate LOOPRING signature.
        """
        security = request.data.pop("security", Security.NONE)
        if security == Security.NONE:
            if request.method == "POST":
                request.data = ujson.dumps(request.params if len(request.data) == 0 else request.data)
                request.params = {}
            return request

        if request.params:
            path = request.path + "?" + urllib.parse.urlencode(request.params, safe=',')
        else:
            request.params = dict()
            path = request.path

        # Add headers
        default_headers = {
            "Content-Type": "*/*",
            "Accept": "application/json",
            'User-Agent': "Trade Robot User-Agent",
            "X-API-KEY": self.key,
        }
        if request.headers != None:
            default_headers.update(request.headers)

        if security == Security.SIGNED:
            ordered_data = self._order_params(request)
            hasher = hashlib.sha256()
            msgBuf = ordered_data.encode('utf-8')
            hasher.update(msgBuf)
            msgHash = int(hasher.hexdigest(), 16) % SNARK_SCALAR_FIELD
            signed = PoseidonEdDSA.sign(msgHash, FQ(int(self.secret)))
            signature = ','.join(str(_) for _ in [signed.sig.R.x, signed.sig.R.y, signed.sig.s])
            default_headers.update({"X-API-SIG": signature})

        request.path = path
        if request.method != "GET":
            request.data = ujson.dumps(request.params if len(request.data) == 0 else request.data)
            request.params = {}
        else:
            request.data = ujson.dumps({})

        if security in [Security.SIGNED, Security.API_KEY]:
            request.headers = default_headers

        return request

    def connect(
            self,
            exchangeId: int,
            key: str,
            secret: str,
            session_number: int,
            proxy_host: str,
            proxy_port: int,
            address: str,
            accountId: int,
    ):
        """
        Initialize connection to REST server.
        """
        self.key = key
        self.exchangeId = exchangeId
        self.secret = secret.encode()
        self.proxy_port = proxy_port
        self.proxy_host = proxy_host
        self.address = address
        self.accountId = accountId

        self.connect_time = (
                int(datetime.now().strftime("%y%m%d%H%M%S")) * self.orderId_limit
        )

        self.init(REST_HOST, proxy_host, proxy_port)
        self.start(session_number)

        self.gateway.write_log("REST API启动成功")

        self.gateway.write_log("start query_time")
        self.query_time()
        self.gateway.write_log("start query_token")
        self.query_market_config()
        self.gateway.write_log("start query_account")
        self.query_account()
        self.gateway.write_log("trade_ws_apis connect")

    def query_time(self):
        """"""
        data = {
            "security": Security.NONE
        }

        added_request = self.add_request(
            "GET",
            path="/api/v2/timestamp",
            callback=self.on_query_time,
            data=data
        )
        self.gateway.write_log(added_request)
        return added_request

    def query_account(self):
        """"""
        data = {
            "security": Security.NONE
        }
        param = {
            "owner": self.address
        }

        self.add_request(
            method="GET",
            path="/api/v2/account",
            callback=self.on_query_account,
            params=param,
            data=data
        )

    def query_apikey(self):
        """"""
        data = {"security": Security.SIGNED}

        param = {
            "accountId": self.accountId,
            "publicKeyX": self.publicKeyX,
            "publicKeyY": self.publicKeyY
        }

        self.add_request(
            method="GET",
            path="/api/v2/apiKey",
            callback=self.on_query_apikey,
            params=param,
            data=data
        )

    def query_balance(self):
        """"""
        data = {"security": Security.API_KEY}

        param = {
            "accountId": self.accountId,
            "tokens": ','.join([str(token.tokenId) for token in self.tokens.values()])
        }

        self.add_request(
            method="GET",
            path="/api/v2/user/balances",
            callback=self.on_query_balance,
            params=param,
            data=data
        )

    def query_order(self):
        """"""
        raise NotImplementedError("Using query_orders")

    def query_orders(self):
        """"""
        data = {"security": Security.API_KEY}

        params = {
            "accountId": self.accountId,
            "start" : 0,
            "end" : (int(time.time()) - self.time_offset) * 1000,
            "status": "processing",
            "limit" : 50
        }

        self.add_request(
            method="GET",
            path="/api/v2/orders",
            callback=self.on_query_orders,
            params=params,
            data=data
        )

    def query_market_config(self):
        """
            query market token and contract config
        """
        data = {"security": Security.NONE}

        params = {}

        self.add_request(
            method="GET",
            path="/api/v2/exchange/tokens",
            callback=self.on_query_token,
            params=params,
            data=data
        )

    def query_contract(self):
        """
            hardcode information as marketInfo API is gone.
        """
        data = {"security": Security.NONE}

        params = {}

        self.add_request(
            method="GET",
            path="/api/v2/exchange/markets",
            callback=self.on_query_contract,
            params=params,
            data=data
        )


    def _new_order_id(self):
        """"""
        with self.order_count_lock:
            self.order_count += 1
            return self.order_count

    def _create_order(self, req):
        bsStr = req.symbol.split("-")
        if not req.symbol in self.contracts:
            self.gateway.write_log("Market dont have " + req.symbol)
            return False, None, None

        if not req.volume:
            self.gateway.write_log(f"{req} is invalid")
            return False, None, None

        contractS = self.tokens[bsStr[0]]
        contractB = self.tokens[bsStr[1]]
        amountS = str(int(10 ** contractS.decimals * req.volume))
        amountB = str(int(10 ** contractB.decimals * req.price * req.volume))
        tokenSId = contractS.tokenId
        tokenBId = contractB.tokenId
        buy = req.direction == Direction.LONG
        if buy:
            tokenSId, tokenBId = tokenBId, tokenSId
            amountS, amountB = amountB, amountS

        clientOrderId = str(self.connect_time + self._new_order_id())
        vt_order = req.create_order_data(
            orderid=clientOrderId,
            gateway_name=self.gateway_name
        )

        if tokenSId in self.failed_orderId and len(self.failed_orderId[tokenSId]) > 0:
            orderId = self.failed_orderId[tokenSId].pop(0)
        else:
            orderId = self.orderId_manager.get_orderId(tokenSId)

        self.gateway.write_log(f"Order: {req.direction} {req.price} {req.volume} orderId {orderId} clientOrderId {clientOrderId}")
        self.gateway.on_order(vt_order)

        # ahead 1 hour
        validSince = int(time.time()) - self.time_offset - 3600
        validUntil = validSince + 60 * 24 * 60 * 60
        maxFeeBips = 50
        allOrNone = 0

        label = 596
        msg_parts = [
            int(self.exchangeId),
            int(orderId),
            int(self.accountId),
            int(tokenSId),
            int(tokenBId),
            int(amountS),
            int(amountB),
            int(allOrNone),
            int(validSince),
            int(validUntil),
            int(maxFeeBips),
            int(buy),
            int(label)
        ]
        PoseidonHashParams = poseidon_params(SNARK_SCALAR_FIELD, 14, 6, 53, b'poseidon', 5, security_target=128)
        msgHash = poseidon(msg_parts, PoseidonHashParams)
        signedMessage = PoseidonEdDSA.sign(msgHash, FQ(int(self.secret)))
        newOrder = {
            "exchangeId": self.exchangeId,
            "orderId": orderId,
            "accountId": self.accountId,
            "tokenSId": tokenSId,
            "tokenBId": tokenBId,
            "amountS": amountS,
            "amountB": amountB,
            "allOrNone": "false",
            "buy": "true" if buy else "false",
            "validSince": validSince,
            "validUntil": validUntil,
            "maxFeeBips": maxFeeBips,
            "label": label,
            "hash": str(msgHash),
            "signatureRx": str(signedMessage.sig.R.x),
            "signatureRy": str(signedMessage.sig.R.y),
            "signatureS": str(signedMessage.sig.s),
            "clientOrderId": clientOrderId,
        }

        self.gateway.write_log(f"create new order {newOrder}")
        return True, vt_order, newOrder

    def send_order(self, req: OrderRequest):
        """"""
        data = {
            "security": Security.API_KEY
        }

        ok, order, newOrder = self._create_order(req)
        if not ok:
            return ""

        headers = {
            "Content-Type": "application/json",
            "X-API-KEY": self.key
        }

        self.add_request(
            method="POST",
            path="/api/v2/order",
            callback=self.on_send_order,
            params=newOrder,
            data=data,
            headers=headers,
            extra=[order],
            on_error=self.on_send_order_error,
            on_failed=self.on_send_order_failed
        )

        return order.vt_orderid

    def cancel_order(self, req: CancelRequest):
        """"""
        self.gateway.write_log(f"cancel_order {req.orderid}")
        data = {
            "security": Security.SIGNED
        }

        params = {
            "accountId": self.accountId,
        }

        if req.orderid != "*":
            params ['clientOrderId'] = req.orderid

        self.add_request(
            method="DELETE",
            path="/api/v2/orders",
            callback=self.on_cancel_order,
            params=params,
            data=data,
        )

    def on_query_time(self, data, request):
        """"""
        self.gateway.write_log(f"on_query_time: {data}")
        if data['resultInfo']['code'] != 0:
            raise AttributeError(f"on_query_time failed {data}")
        local_time = int(time.time() * 1000)
        server_time = int(data["data"])
        self.time_offset = int((local_time - server_time) / 1000)

    def on_query_account(self, data, request):
        """"""
        self.gateway.write_log(f"on_query_account {data}")
        if data['resultInfo']['code'] != 0:
            raise AttributeError(f"on_query_account failed {data}")

        account_data = data['data']
        self.accountId = account_data['accountId']
        self.publicKeyX = account_data['publicKeyX']
        self.publicKeyY = account_data['publicKeyY']

        self.gateway.write_log("账户信息查询成功")
        self.gateway.write_log("start get_apiKey")
        self.query_apikey()

    def on_query_apikey(self, data, request):
        self.gateway.write_log(f"on_query_apikey {data}")
        if data['resultInfo']['code'] != 0:
            raise AttributeError(f"on_query_account failed {data}")

        self.key = data["data"]

        self.gateway.write_log("start query_balance")
        self.query_balance()

        self.gateway.write_log("start query_orders")
        self.query_orders()

    def on_query_balance(self, data, request):
        self.gateway.write_log(f"on_query_balance {data}")
        if data['resultInfo']['code'] != 0:
            raise AttributeError(f"on_query_balance failed {data}")

        for balance in data['data']:
            accountId = balance['accountId']
            token_symbol = "LRC"
            decimals = 18
            tokenAmount = balance['totalAmount']
            frozenAmount = balance['amountLocked']
            for token in self.tokens.keys():
                if self.tokens[token].tokenId == balance['tokenId']:
                    token_symbol = self.tokens[token].symbol
                    decimals = self.tokens[token].decimals
                    account = AccountData(
                        accountid=token_symbol,
                        balance=float(tokenAmount)/(10**decimals),
                        frozen=float(frozenAmount)/(10**decimals),
                        gateway_name=self.gateway_name
                    )
                    self.gateway.write_log(f"账户余额 {account}")
                    self.gateway.on_account(account)

        self.gateway.write_log("账户余额查询成功")

    def on_query_orderId(self, data, request):
        self.gateway.write_log(f"on_query_orderId {request} {data}")
        if data['resultInfo']['code'] != 0:
            raise AttributeError(f"on_query_orderId failed {data}")

        tokenId = request.params['tokenSId']
        self.orderId_manager.put_orderId(tokenId, int(data['data']))

    def on_query_orders(self, data, request):
        self.gateway.write_log(f"on_query_orders {data}")

        for order in data['data']['orders']:
            # TODO: use correct decimals to calc volume
            decimals = self.contracts[order['market']].decimals
            volume = int(order["size"])/(10**decimals)
            order_data = OrderData(
                orderid=order["clientOrderId"],
                symbol=order["market"],
                exchange=Exchange.LOOPRING,
                price=float(order["price"]),
                volume=volume,
                type=OrderType.LIMIT,
                direction=DIRECTION_LOOPRING2VT[order["side"]],
                status=STATUS_LOOPRING2VT.get(order["status"], None),
                datetime=datetime.fromtimestamp(float(order['createdAt']) / 1000).__str__(),
                gateway_name=self.gateway_name,
            )
            self.gateway.on_order(order_data)

        self.gateway.write_log("所有Orders查询成功")

    def on_query_token(self, data, request):
        """"""
        self.gateway.write_log(f"on_query_token: {data}")
        for d in data["data"]:
            contract = ContractData(
                symbol=d["symbol"],
                name=d["symbol"],
                exchange=Exchange.LOOPRING,
                size=1,
                address=d['address'],
                decimals=d['decimals'],
                tokenId=d['tokenId'],
                product=Product.SPOT,
                pricetick=0.0,
                min_volume=int(d['minOrderAmount'])/10**int(d['decimals']),
                history_data=True,
                gateway_name=self.gateway_name,
            )
            self.gateway.on_contract(contract)
            self.tokens[d['symbol']] = contract
            self.query_orderId(d['tokenId'])
        self.gateway.write_log(f"on_query_token success: {self.tokens}")
        self.gateway.write_log("start query_contract")
        self.query_contract()

    def on_query_contract(self, data, requet):
        self.gateway.write_log(f"on_query_contract: {data}")
        decimals = 18
        for d in data["data"]:
            tokens = re.match("(\w+)-(\w+)", d['market'])
            assert tokens is not None
            base_token = tokens.groups()[0]
            assert self.tokens[base_token].tokenId == d['baseTokenId']
            decimals = self.tokens[base_token].decimals

            contract = ContractData(
                symbol=d["market"],
                name=d["market"],
                exchange=Exchange.LOOPRING,
                size=1,
                decimals=decimals,
                min_volume=0.0001,
                product=Product.SPOT,
                pricetick=float(1)/(10**d['precisionForPrice']),
                history_data=True,
                gateway_name=self.gateway_name,
            )
            self.gateway.on_contract(contract)
            self.contracts[d['market']] = contract

            symbol_name_map[contract.symbol] = contract.name

        self.gateway.write_log(f"Contract 信息查询成功 {symbol_name_map}")

    def on_send_order(self, data, request):
        self.gateway.write_log(f"on_send_order {data}")
        if data['resultInfo']['code'] != 0:
            order = request.extra[0]
            order.status = Status.REJECTED
            # {'error': {'code': 102007, 'message': 'order existed, please check detail order info'}}
            if 'order existed' in data['resultInfo']['message']:
                self.gateway.on_order(order)
                return

            newest_order_id = 0
            # if {'error': {'code': 102004, 'message': 'the newest order id should be 57451'}}
            if 'the newest order id should be' in data['resultInfo']['message']:
                newest_order_id = re.search('the newest order id should be (\d+)', data['resultInfo']['message']).groups()[0]

            self.on_error_recover_orderId(request, int(newest_order_id))
            self.gateway.on_order(order)
            return

        order = request.extra[0]
        order.status = Status.NOTTRADED
        self.gateway.on_order(order)
        """"""
        pass

    def on_send_order_failed(self, status_code: str, request: Request):
        """
        Callback when sending order failed on server.
        """
        self.gateway.write_log(f"Error: on_send_order_failed: {status_code} {request}")
        orders = request.extra
        for order in orders:
            order.status = Status.REJECTED
            #align srv orderId
            self.on_error_recover_orderId(request)
            self.gateway.on_order(order)
            # delay 150ms to avoid high TPS in srv.
            sleep(0.15)

    def on_send_order_error(
            self, exception_type: type, exception_value: Exception, tb, request: Request
    ):
        """
        Callback when sending order caused exception.
        """
        self.gateway.write_log(f"on_send_order_error {exception_value} {request}")
        orders = request.extra
        for order in orders:
            order.status = Status.REJECTED
            #align srv orderId
            self.on_error_recover_orderId(request)
            self.gateway.on_order(order)

        # Record exception if not ConnectionError
        if not issubclass(exception_type, ConnectionError):
            self.on_error(exception_type, exception_value, tb, request)
        else:
            # delay 150ms to avoid high TPS in srv.
            sleep(0.15)

    def on_error_recover_orderId(self, request, newest_order_id: int = 0):
        self.gateway.write_log(f"on_error_recover_orderId: {request} {newest_order_id}")
        order_detail = ujson.loads(request.data)
        orderId = order_detail.get('orderId', None)
        tokenSId = order_detail.get('tokenSId', None)
        if orderId is not None and tokenSId is not None:
            if newest_order_id != 0:
                if orderId > newest_order_id:
                    reuse_tokenS_orderIds = self.failed_orderId.get(tokenSId, [])
                    if orderId not in reuse_tokenS_orderIds:
                        reuse_tokenS_orderIds.append(orderId)
                        self.failed_orderId[tokenSId] = reuse_tokenS_orderIds

                self.orderId_manager.put_orderId(tokenSId, newest_order_id)
                self.gateway.write_log(f"on_error_recover_orderId: updated orderid of {tokenSId} to {newest_order_id}")
            else:
                self.gateway.write_log(f"on_error_recover_orderId: reuse orderId {orderId}")
                reuse_tokenS_orderIds = self.failed_orderId.get(tokenSId, [])
                reuse_tokenS_orderIds.append(orderId)
                self.failed_orderId[tokenSId] = reuse_tokenS_orderIds
        else:
            self.gateway.write_log(f"ERROR: recover orderId from request = {request} failed.")

    def on_failed(self, status_code: int, request: Request):
        """
        Callback to handle request failed.
        """
        msg = f"Error: 请求 {request} 失败，状态码：{status_code}"
        self.gateway.write_log(msg)
        # delay 150ms to avoid high TPS in srv.
        sleep(0.15)

    def on_error(self, exception_type: type, exception_value: Exception, tb, request: Request):
        """
        Callback to handler request exception.
        """
        msg = f"Error: 触发异常，状态码：{exception_type}，信息：{exception_value}"
        self.gateway.write_log(msg)

        sys.stderr.write(
            self.exception_detail(exception_type, exception_value, tb, request)
        )
        # delay 150ms to avoid high TPS in srv.
        sleep(0.15)

    def on_cancel_order(self, data, request):
        if data["resultInfo"]["code"] == 0:
            if "clientOrderId" in request.params:
                clientOrderId = request.param['clientOrderId']
                assert clientOrderId in self.gateway.orders
                order = self.gateway.orders[clientOrderId]
                order.status = Status.CANCELLED
                self.gateway.on_order(order)
        else:
            self.gateway.write_log(f"Cancel order {request.params} error {data['resultInfo']['message']}.")
        pass

    def query_orderId(self, tokenId):
        """"""
        data = {
            "security": Security.API_KEY
        }
        params = {
            "accountId": self.accountId,
            "tokenSId": tokenId
        }
        self.add_request(
            method="GET",
            path="/api/v2/orderId",
            callback=self.on_query_orderId,
            params=params,
            data=data
        )

    def query_history(self, req: HistoryRequest):
        """"""
        history = []
        limit = 1000
        start_time = int(datetime.timestamp(req.start))

        while True:
            # Create query params
            params = {
                "market": req.symbol,
                "interval": INTERVAL_VT2LOOPRING[req.interval],
                "limit": limit,
                "start": start_time * 1000,  # convert to millisecond
            }

            # Add end time if specified
            if req.end:
                end_time = int(datetime.timestamp(req.end))
                params["end"] = end_time * 1000  # convert to millisecond

            # Get response from server
            resp = self.request(
                "GET",
                "/api/v2/candlestick",
                data={"security": Security.NONE},
                params=params
            )

            # Break if request failed with other status code
            if resp.status_code // 100 != 2:
                msg = f"Error: 获取历史数据失败，状态码：{resp.status_code}，信息：{resp.text}"
                self.gateway.write_log(msg)
                break
            else:
                data = resp.json()
                if not data:
                    msg = f"Error: 获取历史数据为空，开始时间：{start_time}"
                    self.gateway.write_log(msg)
                    break

                buf = []

                for l in data['data']:
                    #[开始时间，交易笔数，开盘价，收盘价，最高价，最低价，Base Token成交总量，Quote Token成交总额]
                    dt = datetime.fromtimestamp(l[0] / 1000)  # convert to second

                    bar = BarData(
                        symbol=req.symbol,
                        exchange=req.exchange,
                        datetime=dt,
                        interval=req.interval,
                        volume=float(l[6]),
                        open_price=float(l[2]),
                        high_price=float(l[4]),
                        low_price=float(l[5]),
                        close_price=float(l[3]),
                        gateway_name=self.gateway_name
                    )
                    buf.append(bar)

                history.extend(buf)

                begin = buf[0].datetime
                end = buf[-1].datetime
                msg = f"获取历史数据成功，{req.symbol} - {req.interval.value}，{begin} - {end}"
                self.gateway.write_log(msg)

                # Break if total data count less than limit (latest date collected)
                if len(data) < limit:
                    break

                # Update start time
                start_dt = bar.datetime + TIMEDELTA_MAP[req.interval]
                start_time = int(datetime.timestamp(start_dt))

        return history

# Tracking own trades
class LoopringTradeWebsocketApi(WebsocketClient):
    """"""

    def __init__(self, gateway):
        """"""
        super().__init__()

        self.gateway = gateway
        self.gateway_name = gateway.gateway_name
        self.subscribe_reqs = {}
        self.last_subscribe_reqs = {}
        self.ping_interval = 60
        self.account_sub = False

    def connect(self, url, proxy_host, proxy_port):
        """"""
        self.init(url, proxy_host, proxy_port)
        self.start()

    def on_disconnected(self):
        """"""
        self.gateway.write_log(f"交易Websocket API连接断开")
        self.last_subscribe_reqs.update(self.subscribe_reqs)
        self.subscribe_reqs.clear()
        self.account_sub = False

    def on_connected(self):
        """"""
        self.gateway.write_log(f"交易Websocket API连接成功")
        # self.gateway.rest_api.query_orders()
        for req in self.last_subscribe_reqs.values():
            self.subscribe(req)

    def subscribe(self, req: SubscribeRequest):
        # subscribe
        self.gateway.write_log(f"交易Websocket API连接 订阅{req}.")
        channels = {
            "op": "sub",
            "sequence": 10000,
            "apiKey": self.gateway.rest_api.key,
            "unsubscribeAll": False, #last account sub works
            "topics": [
                {
                    "topic": "account"
                }
            ]
        }
        self.account_sub = True
        self.send_packet(channels)

        channels = {
            "op": "sub",
            "sequence": 20000 + len(self.subscribe_reqs),
            "apiKey": self.gateway.rest_api.key,
            "unsubscribeAll": False, #keep previous sub
            "topics": [
                {
                    "topic": "order",
                    "market": req.symbol
                }
            ]
        }
        self.subscribe_reqs[req.symbol] = req
        self.send_packet(channels)

    def on_packet(self, packet: dict):  # type: (dict)->None
        """"""
        # self.gateway.write_log(f"交易on_packet {packet}")
        if packet == "ping":
            self._send_text("pong")
            return

        if 'result' in packet:
            result = packet['result']
            status = result['status']
            if status != 'OK':
                self.gateway.write_log("LoopringDEX trade WS Error status:" + status)
                raise ConnectionError(f"{result}")

        if "topic" in packet:
            topic = packet['topic']['topic']
            if topic == "account":
                self.on_account(packet)
            elif topic == "order":
                self.on_order(packet)

    def on_account(self, packet):
        self.gateway.write_log(f"交易on_account {packet}")
        """"""
        d = packet["data"]
        for token in self.gateway.rest_api.tokens.keys():
            if self.gateway.rest_api.tokens[token].tokenId== d["tokenId"]:
                accountId = self.gateway.rest_api.tokens[token].symbol
                decimal = self.gateway.rest_api.tokens[token].decimals
                account = AccountData(
                    accountid=accountId,
                    balance=float(d["totalAmount"])/(10**decimal),
                    frozen=float(d["amountLocked"])/(10**decimal),
                    gateway_name=self.gateway_name
                )
                self.gateway.on_account(account)

    def on_order(self, packet):
        """"""
        self.gateway.write_log(f"交易on_order {packet}")
        data = packet["data"]
        market = data['market']
        orderid = data["clientOrderId"]
        decimals = self.gateway.rest_api.contracts[market].decimals
        status = data["status"]
        if status == "processing" and "filledSize" in data and int(data['filledSize']) > 0:
            status = "filled"

        order = OrderData(
            symbol=market,
            exchange=Exchange.LOOPRING,
            orderid=orderid,
            direction=DIRECTION_LOOPRING2VT[data["side"]],
            price=float(data["price"]),
            volume=float(data["size"])/(10**decimals),    # TODO: decimals
            traded=float(data["filledSize"])/(10**decimals),
            status=STATUS_LOOPRING2VT[status],
            datetime=datetime.fromtimestamp(float(packet["ts"]) / 1000).__str__(),
            gateway_name=self.gateway_name
        )

        self.gateway.on_order(order)

    @staticmethod
    def unpack_data(data: str):
        """
        Default serialization format is json.

        override this method if you want to use other serialization format.
        """
        if "ping" == data:
            return data
        return ujson.loads(data)

    def _ping(self):
        pass

class LoopringDataWebsocketApi(WebsocketClient):
    """"""

    def __init__(self, gateway):
        """"""
        super().__init__()

        self.gateway = gateway
        self.gateway_name = gateway.gateway_name
        self.ping_interval = 60

        self.ticks = {}
        self.last_tick_timestampe = 0
        self.last_packet_timestampe = 0
        self.subscribe_reqs = {}
        self.last_subscribe_reqs = {}

    def connect(self, proxy_host: str, proxy_port: int):
        """"""
        self.gateway.write_log("行情Websocket API开始connect")
        self.proxy_host = proxy_host
        self.proxy_port = proxy_port

        url = WEBSOCKET_DATA_HOST
        self.init(url, self.proxy_host, self.proxy_port)
        self.start()

    def on_disconnected(self):
        """"""
        self.gateway.write_log(f"行情Websocket API连接断开: subscribed reqs = {self.subscribe_reqs}")
        self.last_subscribe_reqs.update(self.subscribe_reqs)
        self.subscribe_reqs.clear()

    def on_connected(self):
        """"""
        self.gateway.write_log(f"行情Websocket API连接刷新: subscribed reqs = {self.last_subscribe_reqs}")
        for req in self.last_subscribe_reqs.values():
            self.subscribe(req)

    def subscribe(self, req: SubscribeRequest):
        self.gateway.write_log(f"行情Websocket subscribe {req} after {self.subscribe_reqs}")
        """"""

        if req.symbol not in symbol_name_map:
            self.gateway.write_log(f"找不到该合约代码{req.symbol}")
            return

        if req.symbol in self.subscribe_reqs:
            self.gateway.write_log(f"已经订阅了合约代码{req.symbol}")
            return

        # Create tick buf data
        tick = self.ticks.get(req.symbol.upper(), TickData(symbol=req.symbol,
                                                           name=symbol_name_map.get(req.symbol, ""),
                                                           exchange=Exchange.LOOPRING,
                                                           datetime=datetime.now(),
                                                           gateway_name=self.gateway_name))
        self.ticks[req.symbol.upper()] = tick
        self.subscribe_reqs[req.symbol] = req

        subscribe_args = []
        # orderbook
        subscribe_args.append(
            {
                "topic"  : "orderbook",
                "market" : req.symbol,
                "level": 0,
                "count": 10,
                "snapshot" : True,
            }
        )
        # market trade
        subscribe_args.append(
            {
                "topic"  : "trade",
                "market" : req.symbol,
            }
        )
        #ticker
        subscribe_args.append(
            {
                "topic"  : "ticker",
                "market" : req.symbol,
            }
        )

        # Create new connection
        channels = {
            "op": "sub",
            "sequence": 30000 + len(self.subscribe_reqs),
            "unsubscribeAll": False,
            "topics": subscribe_args
        }
        self.send_packet(channels)

    def on_packet(self, packet):
        # self.gateway.write_log(f"行情on_packet {packet}")
        if packet == "ping":
            self.gateway.write_log("行情send_pong")
            self._send_text("pong")
            return

        jsonData = ujson.loads(ujson.dumps(eval(str(packet))))
        # subscribe status code
        if 'result' in jsonData:
            result = jsonData['result']
            status = result['status']
            if status != 'OK':
                self.gateway.write_log("LoopringDEX data WS Error status:" + status)
                raise ConnectionError(f"{result}")

        # real data streaming
        if 'topic' in jsonData:
            topics = jsonData['topic']
            if topics['topic'] == "trade":
                # "topics": { "topic": "trade", "market": "LRC-ETH" },
                # "ts": 1584717910000,
                # "data": [
                #     [
                #         "1584717910000",  //timestamp
                #         "123456789",  //tradeId
                #         "buy",  //side
                #         "500000",  //size 
                #         "0.0008",  //price
                #         "100"  //fee
                #     ]
                # ]
                # trade data
                market = topics['market']
                datas = jsonData['data']
                for data in datas:
                    order_direction = Direction.LONG
                    if data[2] == 'sell':
                        order_direction = Direction.SHORT

                    decimals = self.gateway.rest_api.contracts[market].decimals
                    trade_dt = datetime.fromtimestamp(float(data[0]) / 1000)
                    trade_time = trade_dt.strftime("%Y-%m-%d %H:%M:%S.%f")
                    trade = TradeData(
                        symbol=market,
                        exchange=Exchange.LOOPRING,
                        orderid=data[1],
                        tradeid=data[1],
                        direction=order_direction,
                        price=data[4],
                        volume=float(data[3])/(10**decimals),   # TODO: decimal
                        datetime=trade_time,
                        gateway_name=self.gateway_name,
                    )
                    self.gateway.on_trade(trade)

            elif topics['topic'] == "candlestick":
                # {'topic': 'ticker&lrc-eth', 'ts': 1574150830158,
                #  'data': {'count': '2', 'timestamp': '1574150830158', 'size': '37600000000000000', 'last': '0.000188',
                #           'open': '0.000188', 'low': '0.000188', 'ask': '0.000189', 'bid': '0.000020', 'high': '0.000188'}}
                market = topics['market']
                decimals = self.gateway.rest_api.contracts[market].decimals
                data = jsonData['data']
                tick = self.ticks[market]
                tick.market = market
                tick.last_volume = tick.volume
                tick.volume = float(data[6])/(10**decimals)    # TODO: decimal
                tick.open_price = float(data[2])
                tick.high_price = float(data[4])
                tick.low_price = float(data[5])
                tick.last_price = float(data[3])
                tick.datetime = datetime.fromtimestamp(float(jsonData['ts']) / 1000)
                # if tick.bid_volume_1 > 0 or tick.ask_volume_1 > 0:
                #     self.gateway.on_tick(copy(tick))
            elif topics['topic'] == "orderbook":
                '''
                "topic": {
                    "topic:": "orderbook",
                    "market": "LRC-USDT",
                    "level": 0,
                    "count": 20,
                    "snapshot": true
                },
                "ts": 1584717910000,
                "startVersion": 1212121,
                "endVersion": "1212123",
                "data": {
                    "bids": [
                        [
                            "295.97",  //price
                            "456781000000000",  //size
                            "3015000000000",  //volume
                            "4"  //count
                        ]
                    ],
                    "asks": [
                        [
                        "298.97",
                        "456781000000000000",
                        "301500000000000",
                        "2"
                        ]
                    ]
                }
                '''
                # depth data
                market = topics['market'].upper()
                data = jsonData['data']

                bids = data['bids']
                asks = data['asks']

                decimals = self.gateway.rest_api.contracts[market].decimals
                tick = self.ticks[market]
                if len(bids) > 0:
                    for n in range(len(bids), 0, -1):
                        price = bids[n-1][0]
                        volume = int(bids[n-1][1])/(10**decimals)
                        tick.__setattr__("bid_price_" + str(n), float(price))
                        tick.__setattr__("bid_volume_" + str(n), float(volume))

                if len(asks) > 0:
                    for n in range(len(asks)):
                        price = asks[n][0]
                        volume = int(asks[n][1])/(10**decimals)
                        tick.__setattr__("ask_price_" + str(n + 1), float(price))
                        tick.__setattr__("ask_volume_" + str(n + 1), float(volume))

                packet_timestampe = jsonData['ts'] / 1000 # in s
                current_timestamp = time.time()

                self.last_packet_timestampe = packet_timestampe
                self.last_tick_timestampe = current_timestamp
                tick.datetime = datetime.fromtimestamp(packet_timestampe)
                self.gateway.on_tick(copy(tick))

    @staticmethod
    def unpack_data(data: str):
        """
        Default serialization format is json.

        override this method if you want to use other serialization format.
        """
        if "ping" == data:
            return data
        return ujson.loads(data)

    def _ping(self):
        pass
