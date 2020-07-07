
import multiprocessing
from time import sleep
from datetime import datetime, time
from logging import INFO

from vnpy.event import EventEngine
from vnpy.trader.setting import SETTINGS
from vnpy.trader.engine import MainEngine

from vnpy.gateway.loopring import LoopringGateway
from vnpy.app.cta_strategy import CtaStrategyApp
from vnpy.app.algo_trading import AlgoTradingApp
from vnpy.app.cta_strategy.base import EVENT_CTA_LOG
from vnpy.app.algo_trading.engine import EVENT_ALGO_LOG


SETTINGS["log.active"] = True
SETTINGS["log.level"] = INFO
SETTINGS["log.console"] = True


loopring_dex_setting = {
    "name" : "Triangle Arbitrage account",
    "exchangeName": "LoopringDEX: Beta 1",
    "exchangeAddress": "0x944644Ea989Ec64c2Ab9eF341D383cEf586A5777",
    "exchangeId": 2,
    "address": "",
    "accountId": 0,
    "key": "",
    "publicKeyX": "",
    "publicKeyY": "",
    "secret": "",
    "session_number": 3,
    "proxy_host": "",
    "proxy_port": ""
}

algo_trading_setting = {
    "template_name": "LiquidMiningAlgo",
    "vt_symbol": "LRC-USDT.LOOPRING",
    "price_offset": 0.5,
    "price_tolerance": 0.4,
    "volume": 400,
    "interval": 30
}

def run_child_algo():
    """
    Running in the child process.
    """
    SETTINGS["log.file"] = True

    event_engine = EventEngine()
    main_engine = MainEngine(event_engine)
    algo_engine : AlgoEngine = main_engine.add_app(AlgoTradingApp)
    loopring_gateway = main_engine.add_gateway(LoopringGateway)

    log_engine = main_engine.get_engine("log")
    event_engine.register(EVENT_ALGO_LOG, log_engine.process_log_event)
    main_engine.write_log("主引擎创建成功")

    log_engine = main_engine.get_engine("log")
    event_engine.register(EVENT_CTA_LOG, log_engine.process_log_event)
    main_engine.write_log("注册日志事件监听")

    main_engine.connect(loopring_dex_setting, loopring_gateway.gateway_name)
    algo_engine.init_engine()
    main_engine.write_log("ALGO策略初始化完成")

    sleep(20)
    algo_engine.start_algo(algo_trading_setting)
    main_engine.write_log(f"Algo [{algo_trading_setting['template_name']}] 启动")

    while True:
        sleep(5)

def run_child():
    """
    Running in the child process.
    """
    SETTINGS["log.file"] = True

    event_engine = EventEngine()
    main_engine = MainEngine(event_engine)
    cta_engine = main_engine.add_app(CtaStrategyApp)
    main_engine.write_log("主引擎创建成功")

    log_engine = main_engine.get_engine("log")
    event_engine.register(EVENT_CTA_LOG, log_engine.process_log_event)
    main_engine.write_log("注册日志事件监听")

    main_engine.connect(loopring_dex_setting, "CTP")
    main_engine.write_log("连接CTP接口")

    sleep(10)

    cta_engine.init_engine()
    main_engine.write_log("CTA策略初始化完成")

    cta_engine.init_all_strategies()
    sleep(60)   # Leave enough time to complete strategy initialization
    main_engine.write_log("CTA策略全部初始化")

    cta_engine.start_all_strategies()
    main_engine.write_log("CTA策略全部启动")

    while True:
        sleep(1)


def run_parent():
    """
    Running in the parent process.
    """
    print("启动CTA策略守护父进程")

    # Chinese futures market trading period (day/night)
    DAY_START = time(8, 45)
    DAY_END = time(15, 30)

    NIGHT_START = time(20, 45)
    NIGHT_END = time(2, 45)

    child_process = None

    while True:
        current_time = datetime.now().time()
        trading = False

        # Check whether in trading period
        if (
            (current_time >= DAY_START and current_time <= DAY_END)
            or (current_time >= NIGHT_START)
            or (current_time <= NIGHT_END)
        ):
            trading = True

        # Start child process in trading period
        if trading and child_process is None:
            print("启动子进程")
            child_process = multiprocessing.Process(target=run_child_algo)
            child_process.start()
            print("子进程启动成功")

        # 非记录时间则退出子进程
        if not trading and child_process is not None:
            print("关闭子进程")
            child_process.terminate()
            child_process.join()
            child_process = None
            print("子进程关闭成功")

        sleep(5)


if __name__ == "__main__":
    run_child_algo()
