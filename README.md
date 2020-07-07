# 路印协议定制VNPY

<p align="center">

  <img src ="https://vnpy.oss-cn-shanghai.aliyuncs.com/vnpy-logo.png"/>

</p>

## 说明

这是为路印交易所[LoopringDEX](https://loopring.io)流动性挖矿定制的vn.py。
vn.py是一套基于Python的开源量化交易系统开发框架，于2015年1月正式发布，在开源社区6年持续不断的贡献下一步步成长为全功能量化交易平台，目前国内外金融机构用户已经超过500家，包括：私募基金、证券自营和资管、期货资管和子公司、高校研究机构、自营交易公司、交易所、Token Fund等。
路印交易所[LoopringDEX](https://loopring.io)是世界上第一个，也是目前唯一的一个运用zkRollup交易协议，在以太坊上搭建的高吞吐量、低成本、非托管、基于订单本的去中心化交易平台。

一起来流动性挖矿吧！

## 安装及运行

1. 安装请参考VNPY的说明。

2. 编辑`example/no_ui/run.py`，指定参数。账户参数需要从路印交易所[LoopringDEX](https://loopring.io)获取，关于如何开通账户请参考路印交易所文档[https://docs.loopring.io/en/](https://docs.loopring.io/en/)

   ```json
   SETTINGS["log.console"] = True	#是否输出日志到屏幕
   
   #账户参数
   loopring_dex_setting = {
       "name" : "流动性挖矿账户",
       "exchangeName": "LoopringDEX: Beta 1",
       "exchangeAddress": "0x944644Ea989Ec64c2Ab9eF341D383cEf586A5777",
       "exchangeId": 2,
       "address": "", 		#address
       "accountId": 0,		#account ID
       "key": "", 			#API key
       "publicKeyX": "", 	#Public Key X
       "publicKeyY": "",	#Public Key X
       "secret": "",		#Secret Key, KEEP IT SECRET!!!
       "session_number": 3,
       "proxy_host": "",
       "proxy_port": ""
   }
   
   #流动性挖矿算法参数
   algo_trading_setting = {
       "template_name": "LiquidMiningAlgo",# 默认运行流动性挖矿
       "vt_symbol": "LRC-USDT.LOOPRING", 	# {MINING_MARKET}.LOOPRING
       "price_offset": 0.7,	# 和市场价的差距,这里是0.7%，通常流动性挖矿1%内都有奖励。
       "price_tolerance": 0.3,	# 价格波动容忍度，0.7+/- 0.3 即 [0.4%, 1.0%]
       "volume": 120,			# 一笔下单量
       "interval": 15,			# 下单间隔时间
   }
   ```

3. cd run_liquid_mining and run `python ../example/no_ui/run.py`。

4. 可以从日志看到实时的下单，也可以从交易所订单页面观察即时的流动性挖矿奖励。



## 补充说明

有关vn.py的详细信息，请访问[VNPY]([www.vnpy.com](http://www.vnpy.com/))



## 联系方式

* [exchange@loopring.io](mailto:exchange@loopring.io)

* [Loopring Discord](https://discord.gg/KkYccYp)

## 版权说明

MIT