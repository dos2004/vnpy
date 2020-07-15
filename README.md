# 路印协议流动性挖矿定制化VNPY

<p align="center">

  <img src ="https://vnpy.oss-cn-shanghai.aliyuncs.com/vnpy-logo.png"/>

</p>

## 说明

这是为路印交易所[LoopringDEX](https://loopring.io)流动性挖矿深度定制的vn.py，精简了大部分核心功能无关的代码，专注于流动性挖矿功能。

vn.py是一套基于Python的开源量化交易系统开发框架，于2015年1月正式发布，在开源社区6年持续不断的贡献下一步步成长为全功能量化交易平台，目前国内外金融机构用户已经超过500家，包括：私募基金、证券自营和资管、期货资管和子公司、高校研究机构、自营交易公司、交易所、Token Fund等。

路印交易所[LoopringDEX](https://loopring.io)是世界上第一个，也是目前唯一的一个运用zkRollup交易协议，在以太坊上搭建的高吞吐量、低成本、非托管、基于订单本的去中心化交易平台。

一起来路印交易所[LoopringDEX](https://loopring.io)流动性挖矿吧！

## 安装及运行

1. 编辑`example/no_ui/run.py`，指定参数。账户参数需要从路印交易所[LoopringDEX](https://loopring.io)获取，关于如何开通账户请参考路印交易所文档[https://docs.loopring.io/en/](https://docs.loopring.io/en/)

   ```python
   SETTINGS["log.console"] = True	#是否输出日志到屏幕，默认为输出
   
   #账户参数，从路印导出粘贴即可
   loopring_dex_setting = {
       "name" : "流动性挖矿账户",
       "exchangeName": "LoopringDEX: Beta 1",
       "exchangeAddress": "0x944644Ea989Ec64c2Ab9eF341D383cEf586A5777",
       "exchangeId": 2,       # exchange ID
       "accountAddress": "1", # account address
       "accountId": 1,        # account ID
       "apiKey": "1",         # API key
       "publicKeyX": "1",     # Public Key X
       "publicKeyY": "1",     # Public Key Y
       "privateKey": "1",     # Secret Key, KEEP IT SECRET!!!
   }
   
   #流动性挖矿算法参数
   algo_trading_setting = {
       "template_name": "LiquidMiningAlgo", # 默认运行流动性挖矿
       
       "vt_symbol": "LRC-USDT.LOOPRING",    # {MINING_MARKET}.LOOPRING
       
       "price_offset": 0.7,                 # 和市场价的差距，这里是0.7%，通常流动性挖矿1%内都有奖励
       
       "price_tolerance": 0.3,              # 市场价格波动容忍度，此处0.3等于将订单价格保持在市场价0.7%+/-0.3%范围，
                                            # 即市场价上下0.4% ~ 1.0%的位置上。一旦市价变化，订单价格超出该范围则重新下单，
                                            # 并将继续保持在新市场价格的0.4%~1.0%。
                                            # 推荐值为略小于price_offset，并且 price_offset + price_tolerance <= 挖矿奖励范围
                                      
       "volume": 120,                       # 单笔订单下单量
       
       "interval": 15,                      # 下单间隔时间,以秒为单位
       
       "min_order_level": 3,                # 订单最高档位，1～5之间，这里的3表示在将订单保持在买3之下，卖3之上。
                                            # 以卖单为例，如果当前订单价格高于目前市场价卖3，则取消订单，并根据 price_offset 重新下单。
                                            # 注意：如果配置不合理或者市场深度不足，可能导致无法下单，即计算得到的订单价格永远低于卖3价（高于买3价）。
       
       "min_pos": -5000,                    # 最小持仓单位，即卖出的LRC数量，小于该值停止流动性挖矿
       
       "max_pos": 5000                      # 最大持仓单位，即买入的LRC数量，大于该值停止流动性挖矿
   }
   ```

2. 根目录运行`docker build --rm -t mining:latest .`，成功以后有两种方式（等价）启动流动性挖矿。

   a. 直接在本机运行`docker run mining:latest`。

   b. 运行`docker run -it mining:latest bash`进入Docker镜像命令行，然后运行`python ../example/no_ui/run.py`。

3. 可以从日志看到实时的下单，从交易所订单页面可以看到即时的流动性挖矿奖励。

4. Ctrl+C 结束镜像运行，正常情况下退出时候会取消所有订单，建议观察日志/交易所页面确认，以免出现意外。

注意：每次run.py参数的改动以后都需要重新运行第2步来重新生成以及运行新的Docker镜像（非常快）。


## 补充说明

有关vn.py的详细信息，请访问[VNPY项目主页](http://www.vnpy.com/)

有关流动性挖矿活动以及奖励计算方法，请查看[路印博客](https://blogs.loopring.org/market-making-competition-cn/)

## 联系方式

* [exchange@loopring.io](mailto:exchange@loopring.io)

* [Loopring Discord](https://discord.gg/KkYccYp)

## 版权说明

MIT
