import msgspec
from typing import Optional, List

class Rate(msgspec.Struct, frozen=True):
    totalRate: Optional[float] = None
    baseRate: Optional[float] = None
    taxes: Optional[float] = None
    currency: Optional[str] = None
    refundable: Optional[bool] = None
    payAtHotel: Optional[bool] = None
    publishedRate: Optional[float] = None
    ourServiceFee: Optional[float] = None
    ourTotalMarkup: Optional[float] = None
    providerId: Optional[str] = None
    providerName: Optional[str] = None
    offers: Optional[List[dict]] = None

class Review(msgspec.Struct, frozen=True):
    rating: Optional[float] = None
    count: Optional[int] = None

class Geocode(msgspec.Struct, frozen=True):
    lat: Optional[float] = None
    long: Optional[float] = None

class City(msgspec.Struct, frozen=True):
    name: Optional[str] = None

class Address(msgspec.Struct, frozen=True):
    line1: Optional[str] = None
    city: Optional[City] = None

class Contact(msgspec.Struct, frozen=True):
    address: Optional[Address] = None

class Facility(msgspec.Struct, frozen=True):
    groupName: Optional[str] = None
    name: Optional[str] = None

class Content(msgspec.Struct, frozen=True):
    id: int | str
    name: str
    brandName: Optional[str] = None
    starRating: Optional[float] = None
    review: Optional[Review] = None
    geocode: Optional[Geocode] = None
    contact: Optional[Contact] = None
    facilities: Optional[List[Facility]] = None

class Hotel(msgspec.Struct, frozen=True):
    id: int | str
    content: Content
    rate: Rate

class Envelope(msgspec.Struct, frozen=True):
    status: str
    token: Optional[str] = None
    completedHotelCount: Optional[int] = None
    expectedHotelCount: Optional[int] = None
    hotels: List[Hotel] = []