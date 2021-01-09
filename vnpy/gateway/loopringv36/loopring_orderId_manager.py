import os
import plyvel
import sys
from time import sleep

from vnpy.trader.setting import SETTINGS

import os
import plyvel
import sys
from time import sleep

from vnpy.trader.setting import SETTINGS

class BaseOrderIdManager:
    def __init__(self):
        self.orderId = [None] * 256
    
    def get_orderId(self, tokenId):
        orderId = self.orderId[tokenId]
        self.orderId[tokenId] = self.orderId[tokenId] + 2
        return orderId

    def put_orderId(self, tokenId, orderId):
        self.orderId[tokenId] = orderId

class SharedOrderIdManager:            
    def __init__(self, path, caps, loopring_client, db_key_prefix):
        self.loopring_client = loopring_client
        self.account_addr = loopring_client.address
        self.db_filename = "LRC-" + str(self.account_addr)
        # TODO: usage lock.
        # self.db_key_prefix = "DB-" + str(loopring_client.gateway.account_usage) + "-"
        self.db_key_prefix = "DB-" + str(self.account_addr) + db_key_prefix + "-"
        self.db_path = os.path.join(path, self.db_filename)
        self.shared_orderId = {} # tokenSId => (next_id, next_id_limit)
        self.id_alloc_cap = caps
        self.write_log = lambda log: loopring_client.gateway.write_log(f"SharedOrderIdManager {log}")
        self.db_client = None
        self.is_locked = lambda : self.db_client != None
        self.write_log(f"init {self.db_path}")
        try_cnt = 5
        while try_cnt > 0:
            try:
                db = plyvel.DB(self.db_path, create_if_missing=True)
                db.close()
                return
            except:
                sleep(1)
                try_cnt -= 1
        
        self.write_log(f"ERROR: fail to init levelDB in {self.db_path}")
        raise EnvironmentError(f"ERROR: fail to init levelDB in {self.db_path}")
    
    def get_orderId(self, tokenId):
        assert tokenId in self.shared_orderId
        assert self.shared_orderId[tokenId][0] <= self.shared_orderId[tokenId][1]
        if self.shared_orderId[tokenId][0] == self.shared_orderId[tokenId][1]:
            try:
                self._lock()
                db_orderId = self._get_db_orderId(tokenId)
                orderId_base = max(db_orderId, self.shared_orderId[tokenId][1])
                self._allocate_orderId(tokenId, orderId_base)
            except:
                self.write_log("Unexpected error:", sys.exc_info()[0])
                raise
            finally:
                self._unlock()
        
        orderId = self.shared_orderId[tokenId][0]
        # update orderId
        if orderId < self.shared_orderId[tokenId][1]:
            self.shared_orderId[tokenId] = (orderId + 1, self.shared_orderId[tokenId][1])
        self.write_log(f"get_orderId {tokenId} {orderId}")
        return orderId

    def put_orderId(self, tokenId, orderId):
        """
            put_orderId():
            set new orderId and allocate few more orderId entries.
            happens either in the begining of client init or sth
            wrong in latest orderId, i.e. a error like "newest
            order id is xxxxx"
        """
        if tokenId not in self.shared_orderId or orderId > self.shared_orderId[tokenId][1]:
            try:
                self._lock()
                # query db to see if anyone has inited.
                db_orderId = self._get_db_orderId(tokenId)
                if db_orderId == -1 or db_orderId <= orderId:
                    self._put_db_orderId(tokenId, orderId)
                self.shared_orderId[tokenId] = (orderId, orderId)
                self.write_log(f"put_orderId {tokenId} {orderId} {db_orderId}")
                return True
            except:
                self.write_log("Unexpected error:", sys.exc_info()[0])
                raise
            finally:
                self._unlock()
        elif orderId <= self.shared_orderId[tokenId][1]:
            # put a less orderId in, do nothing, normally means others have init the db.
            return True
        
        self.write_log(f"Unexpected error: {tokenId} orderid {orderId} is invalid in {self.shared_orderId[tokenId]}")
        return False

    def _lock(self):
        #TODO: lock on tokenID.
        self.write_log("lock()")
        try_cnt = 5
        while try_cnt > 0:
            try:
                self.db_client = plyvel.DB(self.db_path, create_if_missing=True)
                return True
            except:
                self.write_log(f"lock conflict, wait 1s.")
                sleep(1)
                try_cnt -= 1
        
        return False

    def _unlock(self):
        self.write_log("unlock()")
        if not self.is_locked():
            return True

        self.db_client.close()
        self.db_client = None
        return True

    def _allocate_orderId(self, tokenId, orderId):
        assert self.is_locked()
        next_orderId_end = orderId  + self.id_alloc_cap
        self._put_db_orderId(tokenId, next_orderId_end)
        self.shared_orderId[tokenId] = (orderId, next_orderId_end)
        self.write_log(f"_allocate_orderId {tokenId} {orderId} to {next_orderId_end}")
        pass

    def _put_db_orderId(self, tokenId, orderId):
        assert self.is_locked()
        key = bytes(self.db_key_prefix + str(tokenId), 'utf-8')
        int_value = orderId
        value = (int_value).to_bytes((int_value.bit_length()+7)//8, 'big')
        self.write_log(f"_put_db_orderId {tokenId} {orderId}")
        self.db_client.put(key, value)
        return value

    def _get_db_orderId(self, tokenId):
        assert self.is_locked()
        key = bytes(self.db_key_prefix + str(tokenId), 'utf-8')
        value = self.db_client.get(key)
        if value is not None:
            self.write_log(f"_get_db_orderId {tokenId} {int.from_bytes(value, 'big')}")
            return int.from_bytes(value, 'big')
        else:
            self.write_log(f"_get_db_orderId {self.db_key_prefix + str(tokenId)} failed, return -1")
            return -1

# class BaseOrderIdManager:
#     def __init__(self):
#         self.orderId = [None] * 256
#         self.offchainId = [None] * 256
    
#     def get_OrderId(self, tokenId):
#         orderId = self.orderId[tokenId]
#         self.orderId[tokenId] += 2
#         return orderId

#     def get_OffchainId(self, tokenId):
#         offchainId = self.offchainId[tokenId]
#         self.offchainId[tokenId] += 2
#         return offchainId

#     def put_StorageId(self, tokenId, orderId, offchainId):
#         assert orderId % 2 == 0 and offchainId % 2 == 1
#         self.orderId[tokenId] = orderId
#         self.offchainId[tokenId] = offchainId

# class SharedOrderIdManager:            
#     def __init__(self, path, caps, loopring_client):
#         self.loopring_client = loopring_client
#         self.account_addr = loopring_client.address
#         self.db_filename = "LRC-" + str(self.account_addr)
#         # TODO: usage lock.
#         # self.db_key_prefix = "DB-" + str(loopring_client.gateway.account_usage) + "-"
#         self.db_key_prefix = "DB-" + str(self.account_addr) + "-"
#         self.db_path = os.path.join(path, self.db_filename)
#         self.shared_orderId = {} # tokenSId => (next_id, next_id_limit)
#         self.shared_offchainId = {} # tokenSId => (next_id, next_id_limit)
#         self.id_alloc_cap = caps
#         self.write_log = lambda log: loopring_client.gateway.write_log(f"SharedOrderIdManager {log}")
#         self.db_client = None
#         self.is_locked = lambda : self.db_client != None
#         self.write_log(f"init {self.db_path}")
#         try_cnt = 5
#         while try_cnt > 0:
#             try:
#                 db = plyvel.DB(self.db_path, create_if_missing=True)
#                 db.close()
#                 return
#             except:
#                 sleep(1)
#                 try_cnt -= 1
        
#         self.write_log(f"ERROR: fail to init levelDB in {self.db_path}")
#         raise EnvironmentError(f"ERROR: fail to init levelDB in {self.db_path}")
    
#     def get_OrderId(self, tokenId):
#         assert tokenId in self.shared_orderId
#         assert self.shared_orderId[tokenId][0] <= self.shared_orderId[tokenId][1]
#         if self.shared_orderId[tokenId][0] == self.shared_orderId[tokenId][1]:
#             try:
#                 self._lock()
#                 db_orderId = self._get_db_orderId(tokenId)
#                 orderId_base = max(db_orderId, self.shared_orderId[tokenId][1])
#                 self._allocate_orderId(tokenId, orderId_base)
#             except:
#                 self.write_log("Unexpected error:", sys.exc_info()[0])
#                 raise
#             finally:
#                 self._unlock()
        
#         orderId = self.shared_orderId[tokenId][0]
#         # update orderId
#         if orderId < self.shared_orderId[tokenId][1]:
#             self.shared_orderId[tokenId] = (orderId + 1, self.shared_orderId[tokenId][1])
#         self.write_log(f"get_StorageId {tokenId} {orderId}")
#         return orderId

#     def get_OffchainId(self, tokenId):
#         assert tokenId in self.shared_offchainId
#         assert self.shared_offchainId[tokenId][0] <= self.shared_offchainId[tokenId][1]
#         if self.shared_offchainId[tokenId][0] == self.shared_offchainId[tokenId][1]:
#             try:
#                 self._lock()
#                 db_orderId = self._get_db_orderId(tokenId)
#                 orderId_base = max(db_orderId, self.shared_offchainId[tokenId][1])
#                 self._allocate_orderId(tokenId, orderId_base)
#             except:
#                 self.write_log("Unexpected error:", sys.exc_info()[0])
#                 raise
#             finally:
#                 self._unlock()
        
#         orderId = self.shared_offchainId[tokenId][0]
#         # update orderId
#         if orderId < self.shared_offchainId[tokenId][1]:
#             self.shared_offchainId[tokenId] = (orderId + 1, self.shared_offchainId[tokenId][1])
#         self.write_log(f"get_OffchainId {tokenId} {orderId}")
#         return orderId

#     def put_StorageId(self, tokenId, orderId, offchainId):
#         return self._put_OffchainId(offchainId) and self._put_OffchainId(orderId)

#     def _put_OrderId(self, tokenId, orderId):
#         """
#             _put_OrderId():
#             set new orderId and allocate few more orderId entries.
#             happens either in the begining of client init or sth
#             wrong in latest orderId, i.e. a error like "newest
#             order id is xxxxx"
#         """
#         if tokenId not in self.shared_orderId or orderId > self.shared_orderId[tokenId][1]:
#             try:
#                 self._lock()
#                 # query db to see if anyone has inited.
#                 db_orderId = self._get_db_orderId(tokenId)
#                 if db_orderId == -1 or db_orderId <= orderId:
#                     self._put_db_orderId(tokenId, orderId)
#                 self.shared_orderId[tokenId] = (orderId, orderId)
#                 self.write_log(f"put_StorageId {tokenId} {orderId} {db_orderId}")
#                 return True
#             except:
#                 self.write_log("Unexpected error:", sys.exc_info()[0])
#                 raise
#             finally:
#                 self._unlock()
#         elif orderId <= self.shared_orderId[tokenId][1]:
#             # put a less orderId in, do nothing, normally means others have init the db.
#             return True
        
#         self.write_log(f"Unexpected error: {tokenId} orderid {orderId} is invalid in {self.shared_orderId[tokenId]}")
#         return False

#     def _put_OffchainId(self, tokenId, orderId):
#         """
#             _put_OffchainId():
#             set new orderId and allocate few more orderId entries.
#             happens either in the begining of client init or sth
#             wrong in latest orderId, i.e. a error like "newest
#             order id is xxxxx"
#         """
#         if tokenId not in self.shared_offchainId or orderId > self.shared_offchainId[tokenId][1]:
#             try:
#                 self._lock()
#                 # query db to see if anyone has inited.
#                 db_orderId = self._get_db_orderId(tokenId)
#                 if db_orderId == -1 or db_orderId <= orderId:
#                     self._put_db_orderId(tokenId, orderId)
#                 self.shared_offchainId[tokenId] = (orderId, orderId)
#                 self.write_log(f"put_StorageId {tokenId} {orderId} {db_orderId}")
#                 return True
#             except:
#                 self.write_log("Unexpected error:", sys.exc_info()[0])
#                 raise
#             finally:
#                 self._unlock()
#         elif orderId <= self.shared_offchainId[tokenId][1]:
#             # put a less orderId in, do nothing, normally means others have init the db.
#             return True
        
#         self.write_log(f"Unexpected error: {tokenId} orderid {orderId} is invalid in {self.shared_offchainId[tokenId]}")
#         return False

#     def _lock(self):
#         #TODO: lock on tokenID.
#         self.write_log("lock()")
#         try_cnt = 5
#         while try_cnt > 0:
#             try:
#                 self.db_client = plyvel.DB(self.db_path, create_if_missing=True)
#                 return True
#             except:
#                 self.write_log(f"lock conflict, wait 1s.")
#                 sleep(1)
#                 try_cnt -= 1
        
#         return False

#     def _unlock(self):
#         self.write_log("unlock()")
#         if not self.is_locked():
#             return True

#         self.db_client.close()
#         self.db_client = None
#         return True

#     def _allocate_orderId(self, tokenId, orderId):
#         assert self.is_locked()
#         next_orderId_end = orderId  + self.id_alloc_cap
#         self._put_db_orderId(tokenId, next_orderId_end)
#         self.shared_orderId[tokenId] = (orderId, next_orderId_end)
#         self.write_log(f"_allocate_orderId {tokenId} {orderId} to {next_orderId_end}")
#         pass

#     def _put_db_orderId(self, tokenId, orderId):
#         assert self.is_locked()
#         key = bytes(self.db_key_prefix + str(tokenId), 'utf-8')
#         int_value = orderId
#         value = (int_value).to_bytes((int_value.bit_length()+7)//8, 'big')
#         self.write_log(f"_put_db_orderId {tokenId} {orderId}")
#         self.db_client.put(key, value)
#         return value

#     def _get_db_orderId(self, tokenId):
#         assert self.is_locked()
#         key = bytes(self.db_key_prefix + str(tokenId), 'utf-8')
#         value = self.db_client.get(key)
#         if value is not None:
#             self.write_log(f"_get_db_orderId {tokenId} {int.from_bytes(value, 'big')}")
#             return int.from_bytes(value, 'big')
#         else:
#             self.write_log(f"_get_db_orderId {self.db_key_prefix + str(tokenId)} failed, return -1")
#             return -1
