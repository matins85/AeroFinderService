from dataclasses import dataclass
from enum import Enum


# Configuration and Constants
class TripType(Enum):
    ONE_WAY = "one-way"
    ROUND_TRIP = "round-trip"


class AirlineGroup(Enum):
    CRANE_AERO = "crane_aero"
    VIDECOM = "videcom"
    OVERLAND = "overland"  # New airline group
    VALUEJET = "valuejet"  # ValueJet airline group
    GREENAFRICA = "greenafrica"  # Green Africa airline group


@dataclass
class FlightSearchConfig:
    """Configuration for flight search parameters"""
    departure_city: str = "Lagos (LOS)"
    arrival_city: str = "Abuja (ABV)"
    departure_date: str = "06 Jun 2025"  # Format: dd MMM yyyy for Crane, dd-MMM-yyyy for Videcom
    return_date: str = "10 Jun 2025"
    adults: int = 1
    children: int = 0
    infants: int = 0
    trip_type: TripType = TripType.ROUND_TRIP


@dataclass
class AirlineConfig:
    """Configuration for each airline"""
    name: str
    url: str
    group: AirlineGroup
    key: str  # Key for response dict


# Airline configurations - All 11 airlines
AIRLINES_CONFIG = [
    # Crane.aero based airlines (6 airlines)
    AirlineConfig("Air Peace", "https://book-airpeace.crane.aero/ibe/availability", AirlineGroup.CRANE_AERO, "airpeace"),
    AirlineConfig("Arik Air", "https://arikair.crane.aero/ibe/availability", AirlineGroup.CRANE_AERO, "arikair"),
    AirlineConfig("Aero Contractors", "https://book-flyaero.crane.aero/ibe/availability", AirlineGroup.CRANE_AERO, "flyaero"),
    AirlineConfig("Ibom Air", "https://book-ibomair.crane.aero/ibe/availability", AirlineGroup.CRANE_AERO, "ibomair"),
    AirlineConfig("NG Eagle", "https://book-ngeagle.crane.aero/ibe/availability", AirlineGroup.CRANE_AERO, "ngeagle"),
    AirlineConfig("UMZA", "https://book-umz.crane.aero/ibe/availability", AirlineGroup.CRANE_AERO, "umza"),

    # Videcom based airlines (3 airlines)
    AirlineConfig("Max Air", "https://customer2.videcom.com/MaxAir/VARS/Public/CustomerPanels/requirementsBS.aspx",
                  AirlineGroup.VIDECOM, "maxair"),
    AirlineConfig("United Nigeria",
                  "https://booking.flyunitednigeria.com/VARS/Public/CustomerPanels/requirementsBS.aspx",
                  AirlineGroup.VIDECOM, "unitednigeria"),
    AirlineConfig("Rano Air", "https://customer3.videcom.com/RanoAir/VARS/Public/CustomerPanels/requirementsBS.aspx",
                  AirlineGroup.VIDECOM, "ranoair"),
    AirlineConfig("Binani Air", "https://customer3.videcom.com/BinaniAir/VARS/Public/CustomerPanels/requirementsBS.aspx",
                  AirlineGroup.VIDECOM, "binaniair"),
                  

    # Overland Airways
    AirlineConfig("Overland Airways", "https://www.overlandairways.com", AirlineGroup.OVERLAND, "overland"),
    
    # ValueJet Airways
    AirlineConfig("ValueJet", "https://flyvaluejet.com", AirlineGroup.VALUEJET, "valuejet"),
    
    # Green Africa Airways
    AirlineConfig("Green Africa", "https://greenafrica.com", AirlineGroup.GREENAFRICA, "greenafrica"),
]

