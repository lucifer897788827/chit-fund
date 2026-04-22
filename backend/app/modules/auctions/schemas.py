from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class AuctionRoomResult(BaseModel):
    winningBidId: int
    winnerMembershipId: int
    winningBidAmount: int
    finalizedAt: datetime


class AuctionRoomResponse(BaseModel):
    sessionId: int
    groupId: int
    auctionMode: str
    commissionMode: str
    commissionValue: int | None = None
    minBidValue: int
    maxBidValue: int
    minIncrement: int
    auctionState: str
    status: str
    cycleNo: int
    serverTime: datetime
    startsAt: datetime
    endsAt: datetime
    canBid: bool
    myMembershipId: int
    myLastBid: int | None
    myBidCount: int = 0
    myBidLimit: int = 0
    myRemainingBidCapacity: int = 0
    mySlotCount: int = 0
    myWonSlotCount: int = 0
    myRemainingSlotCount: int = 0
    slotCount: int = 0
    wonSlotCount: int = 0
    remainingSlotCount: int = 0
    validBidCount: int = 0
    finalizationMessage: str | None = None
    result: AuctionRoomResult | None = None


class BidCreate(BaseModel):
    membershipId: int
    bidAmount: int
    idempotencyKey: str


class BidResponse(BaseModel):
    accepted: bool
    bidId: int
    placedAt: datetime
    sessionStatus: str
    room: AuctionRoomResponse | None = None


class AuctionFinalizeSummary(BaseModel):
    sessionId: int
    status: str
    totalBids: int
    validBidCount: int | None = None
    auctionResultId: int | None = None
    winnerMembershipId: int | None = None
    winnerMembershipNo: int | None = None
    winnerName: str | None = None
    winningBidId: int | None = None
    winningBidAmount: int | None = None
    ownerCommissionAmount: int | None = None
    dividendPoolAmount: int | None = None
    dividendPerMemberAmount: int | None = None
    winnerPayoutAmount: int | None = None


class AuctionFinalizeResponse(BaseModel):
    sessionId: int
    groupId: int
    auctionMode: str
    commissionMode: str
    commissionValue: int | None = None
    cycleNo: int
    status: str
    closedAt: datetime
    finalizedAt: datetime
    closedByUserId: int
    finalizedByUserId: int
    finalizedByName: str | None = None
    finalizationMessage: str | None = None
    resultSummary: AuctionFinalizeSummary
    console: OwnerAuctionConsoleResponse | None = None


class OwnerAuctionConsoleResponse(BaseModel):
    sessionId: int
    groupTitle: str
    groupCode: str
    auctionMode: str
    commissionMode: str
    commissionValue: int | None = None
    minBidValue: int
    maxBidValue: int
    minIncrement: int
    auctionState: str
    cycleNo: int
    status: str
    scheduledStartAt: datetime | None = None
    actualStartAt: datetime | None = None
    actualEndAt: datetime | None = None
    startTime: datetime | None = None
    endTime: datetime | None = None
    serverTime: datetime
    totalBidCount: int
    validBidCount: int
    highestBidAmount: int | None = None
    highestBidMembershipNo: int | None = None
    highestBidderName: str | None = None
    canFinalize: bool
    auctionResultId: int | None = None
    finalizedAt: datetime | None = None
    finalizedByName: str | None = None
    winnerMembershipId: int | None = None
    winnerMembershipNo: int | None = None
    winnerName: str | None = None
    winningBidId: int | None = None
    winningBidAmount: int | None = None
    ownerCommissionAmount: int | None = None
    dividendPoolAmount: int | None = None
    dividendPerMemberAmount: int | None = None
    winnerPayoutAmount: int | None = None
    finalizationMessage: str | None = None
