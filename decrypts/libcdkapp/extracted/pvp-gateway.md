# ACIES PVP Gateway Static Inventory

PVPGateway symbols: `130`. Requests: `59`. Receives: `55`.

The buffer operation column is a heuristic disassembly pass over `CSBuffer::read*` and `write*` calls. Immediate values in parentheses are the latest nearby `w1` constant, useful for spotting packet opcodes and literal fields.

| Symbol | Address | CSBuffer ops |
| --- | --- | --- |
| `PVPGateway::receiveChannelBlock()` | `0x500560` | readLong |
| `PVPGateway::receiveChannelChat()` | `0x5002e0` |  |
| `PVPGateway::receiveChannelEnter()` | `0x4ffff4` | readBoolean, readBoolean |
| `PVPGateway::receiveChannelExit()` | `0x500198` | readBoolean |
| `PVPGateway::receiveChatFail()` | `0x5005e8` | readByte, readInt |
| `PVPGateway::receiveClanChat()` | `0x4fe1e4` |  |
| `PVPGateway::receiveClanChatHistory()` | `0x4fe428` | readLong, readLong, readLength |
| `PVPGateway::receiveClanMemberStates()` | `0x4fe76c` | readLength(255), readLong |
| `PVPGateway::receiveClanNotification()` | `0x4fe07c` | readLong, readBoolean |
| `PVPGateway::receiveFriendAccept()` | `0x4fed64` | readByte, readInt, readString |
| `PVPGateway::receiveFriendDeny()` | `0x4ff12c` | readByte, readLong, readInt, readString |
| `PVPGateway::receiveFriendRemove()` | `0x4ff420` | readByte, readLong, readInt, readString |
| `PVPGateway::receiveFriendRequest()` | `0x4fe864` | readByte, readInt, readString |
| `PVPGateway::receiveLogin()` | `0x4f9228` | readString, readLength, readLength, readLength(255), readLong |
| `PVPGateway::receiveMatchChat()` | `0x4fd9e8` | readBoolean, readByte, readInt, readString |
| `PVPGateway::receiveMatchCommand()` | `0x4fdc08` | readByte, readInt, readFloat |
| `PVPGateway::receiveMatchCreate()` | `0x4fb500` |  |
| `PVPGateway::receiveMatchEnter()` | `0x4fb684` | readByte, readByte, readShort |
| `PVPGateway::receiveMatchExit()` | `0x4fbbf8` | readByte, readByte, readInt, readLong |
| `PVPGateway::receiveMatchExpire()` | `0x4fcbf8` | readBoolean, readInt |
| `PVPGateway::receiveMatchInvite()` | `0x4fc84c` | readBoolean, readInt |
| `PVPGateway::receiveMatchLevelCorrection()` | `0x4fc0d4` | readByte |
| `PVPGateway::receiveMatchObserverDelay()` | `0x4fc1fc` | readShort |
| `PVPGateway::receiveMatchPause()` | `0x4fdd90` | readBoolean, readByte, readInt, readBoolean |
| `PVPGateway::receiveMatchPredict()` | `0x4fdf1c` | readShort, readShort, readLong, readByte |
| `PVPGateway::receiveMatchQuit()` | `0x4fc5c0` | readInt |
| `PVPGateway::receiveMatchReady()` | `0x4fd67c` |  |
| `PVPGateway::receiveMatchRefuse()` | `0x4fca94` | readBoolean |
| `PVPGateway::receiveMatchSlot()` | `0x4fc324` | readByte, readByte, readBoolean |
| `PVPGateway::receiveMatchStart()` | `0x4fd788` | readLong, readShort |
| `PVPGateway::receiveMatchSwap()` | `0x4fcd40` | readBoolean, readByte, readByte, readInt, readByte |
| `PVPGateway::receiveMatchSync()` | `0x4fd8c4` |  |
| `PVPGateway::receiveMessage()` | `0x500720` | readByte |
| `PVPGateway::receiveNoticeList()` | `0x4ffe14` |  |
| `PVPGateway::receivePacket()` | `0x4f8da4` | readByte, readByte, readInt, readInt, readByte, readByte, readByte, readLong |
| `PVPGateway::receivePartyBack()` | `0x4fb4bc` | readByte |
| `PVPGateway::receivePartyChat()` | `0x4fb2c0` | readByte, readString |
| `PVPGateway::receivePartyCreate()` | `0x4f9cc8` |  |
| `PVPGateway::receivePartyEnter()` | `0x4f9e70` | readByte, readByte |
| `PVPGateway::receivePartyExit()` | `0x4fa224` | readByte, readLong, readByte |
| `PVPGateway::receivePartyExpire()` | `0x4facd0` | readString |
| `PVPGateway::receivePartyInvite()` | `0x4fa920` | readBoolean, readString |
| `PVPGateway::receivePartyMap()` | `0x4fa590` | readBoolean |
| `PVPGateway::receivePartyMatch()` | `0x4fb288` | readByte |
| `PVPGateway::receivePartyRedirect()` | `0x4fadf8` |  |
| `PVPGateway::receivePartyRefuse()` | `0x4fab6c` | readBoolean |
| `PVPGateway::receivePartySlot()` | `0x4fa700` | readByte |
| `PVPGateway::receivePartyStart()` | `0x4faf1c` | readByte, readByte |
| `PVPGateway::receivePartySync()` | `0x4fb2bc` |  |
| `PVPGateway::receiveShutdown()` | `0x500890` |  |
| `PVPGateway::receiveSocketEvent(CSSocket*, CSSocketEvent)` | `0x5009a4` | writeByte(100) |
| `PVPGateway::receiveUpdateProfile()` | `0x4f99c8` |  |
| `PVPGateway::receiveUpdateState()` | `0x4f96a4` | readLong, readLong |
| `PVPGateway::receiveUserChat()` | `0x4ff84c` | readByte, readString |
| `PVPGateway::receiveUserState()` | `0x4ff714` | readLong |
| `PVPGateway::requestArenaDeck()` | `0x503fb8` | writeByte(55) |
| `PVPGateway::requestChannelChat(char const*)` | `0x503d5c` | writeByte(51), writeString(51) |
| `PVPGateway::requestChannelEnter()` | `0x503b70` |  |
| `PVPGateway::requestChannelEnter(char const*, char const*)` | `0x503bd4` | writeByte(49), writeString(49), writeString(49) |
| `PVPGateway::requestChannelExit()` | `0x503cb0` | writeByte(50) |
| `PVPGateway::requestClanChat(char const*)` | `0x503408` | writeByte(39), writeString(39) |
| `PVPGateway::requestClanChatConfirm()` | `0x503e60` | writeLong(16), writeLong, writeToFile |
| `PVPGateway::requestClanDeck()` | `0x503f04` | writeByte(54) |
| `PVPGateway::requestClanNotification(long, long, bool)` | `0x503320` | writeByte(38), writeLong(38), writeLong(38), writeBoolean |
| `PVPGateway::requestConnect()` | `0x500e60` |  |
| `PVPGateway::requestFriendAccept(User const*)` | `0x5035a0` | writeByte(43) |
| `PVPGateway::requestFriendDeny(long)` | `0x50365c` | writeByte(44), writeLong(44) |
| `PVPGateway::requestFriendRemove(long)` | `0x503718` | writeByte(45), writeLong(45) |
| `PVPGateway::requestFriendRequest(UserThumb const*)` | `0x5034e4` | writeByte(42) |
| `PVPGateway::requestLanguage()` | `0x50406c` | writeByte(56), writeString(56) |
| `PVPGateway::requestLogin(bool)` | `0x500ee0` | writeByte, writeShort(18), writeString, writeShort(1), writeShort(1), writeShort(23), writeShort(23), writeLong, writeString, writeBoolean, writeBoolean, writeBoolean(1), writeBoolean, writeLength, writeShort, writeShort, writeLength, writeShort, writeShort, writeShort, writeShort, writeBoolean(1), writeLength, writeShort |
| `PVPGateway::requestMatchAuto(bool)` | `0x503030` | writeByte(34), writeBoolean(34) |
| `PVPGateway::requestMatchChat(char const*, bool)` | `0x502d84` | writeByte(31), writeString(31), writeBoolean(31) |
| `PVPGateway::requestMatchCommand(void const*, unsigned int)` | `0x502e5c` | writeByte(32) |
| `PVPGateway::requestMatchCreate(GameOnlineMode, GameLevelCorrection, int, int, int, MapThumb const*, char const*)` | `0x5022dc` | writeByte(17), writeByte(17), writeByte(17), writeShort, writeShort, writeShort, writeString, writeByte, writeByte |
| `PVPGateway::requestMatchEnter(unsigned int, unsigned int, bool)` | `0x502460` | writeByte(18), writeInt(18), writeInt(18), writeBoolean |
| `PVPGateway::requestMatchExit()` | `0x502548` | writeByte(19) |
| `PVPGateway::requestMatchInvite(UserThumb const*)` | `0x502900` | writeByte(24) |
| `PVPGateway::requestMatchLatency(int, int, float, unsigned int)` | `0x502f2c` | writeByte(33), writeByte(33), writeByte(33), writeFloat, writeInt |
| `PVPGateway::requestMatchLevelCorrection(GameLevelCorrection)` | `0x5025f4` | writeByte(20), writeByte(20) |
| `PVPGateway::requestMatchObserverDelay(int)` | `0x5026b0` | writeByte(21), writeShort(21) |
| `PVPGateway::requestMatchPause(bool)` | `0x5030ec` | writeByte(35), writeBoolean(35) |
| `PVPGateway::requestMatchPredict(int)` | `0x5031a8` | writeByte(36), writeByte(36) |
| `PVPGateway::requestMatchQuit(long)` | `0x502844` | writeByte(23), writeLong(23) |
| `PVPGateway::requestMatchReady()` | `0x502b6c` | writeByte(28) |
| `PVPGateway::requestMatchRefuse(long, bool)` | `0x5029bc` | writeByte(25), writeLong(25), writeBoolean(25) |
| `PVPGateway::requestMatchResult(GameResult)` | `0x503264` | writeByte(37), writeByte(37) |
| `PVPGateway::requestMatchSlot(int, GameControl)` | `0x50276c` | writeByte(22), writeByte(22), writeByte(22) |
| `PVPGateway::requestMatchStart()` | `0x502c18` | writeByte(29) |
| `PVPGateway::requestMatchSwap(long, int)` | `0x502a94` | writeByte(27), writeLong(27), writeByte(27) |
| `PVPGateway::requestMatchSync()` | `0x502cc4` | writeByte(30) |
| `PVPGateway::requestMessageCardObtain(AssetIndex2 const&)` | `0x504124` | writeByte(57), writeByte(57) |
| `PVPGateway::requestPartyBack()` | `0x502230` | writeByte(16) |
| `PVPGateway::requestPartyChat(char const*)` | `0x502174` | writeByte(15), writeString(15) |
| `PVPGateway::requestPartyCreate(GameOnlineMode, int, int, int, char const*, bool)` | `0x5019d4` | writeByte(3), writeByte(3), writeByte(3), writeByte, writeByte, writeString, writeBoolean |
| `PVPGateway::requestPartyEnter(char const*)` | `0x501b04` | writeByte(4), writeString(4) |
| `PVPGateway::requestPartyExit()` | `0x501bc0` | writeByte(5) |
| `PVPGateway::requestPartyInvite(UserThumb const*)` | `0x501df8` | writeByte(8) |
| `PVPGateway::requestPartyMap(AssetIndex4 const*)` | `0x501c6c` | writeByte(6), writeBoolean(6) |
| `PVPGateway::requestPartyRefuse(long, bool)` | `0x501eb4` | writeByte(9), writeLong(9), writeBoolean(9) |
| `PVPGateway::requestPartySlot(int)` | `0x501d3c` | writeByte(7), writeByte(7) |
| `PVPGateway::requestPartyStart(bool)` | `0x501f8c` | writeByte(12), writeBoolean(12) |
| `PVPGateway::requestPartySync()` | `0x5020c8` | writeByte(14) |
| `PVPGateway::requestPing()` | `0x500b98` | writeByte(100) |
| `PVPGateway::requestShutdown(bool)` | `0x4f87b4` |  |
| `PVPGateway::requestUpdateProfile(bool)` | `0x5018f4` | writeByte(2), writeBoolean |
| `PVPGateway::requestUpdateState(UserState const*)` | `0x501830` | writeByte(1) |
| `PVPGateway::requestUserBlock(long)` | `0x5041e0` |  |
| `PVPGateway::requestUserChat(UserThumb const*, char const*)` | `0x503890` | writeByte(47), writeString(47) |
| `PVPGateway::requestUserChatClose(long)` | `0x503abc` |  |
| `PVPGateway::requestUserChatConfirm(long)` | `0x503a94` |  |
| `PVPGateway::requestUserChatCreate(UserThumb const*)` | `0x503974` |  |
| `PVPGateway::requestUserState(long)` | `0x5037d4` | writeByte(46), writeLong(46) |
| `PVPGateway::requestUserUnblock(long)` | `0x5041f0` |  |
