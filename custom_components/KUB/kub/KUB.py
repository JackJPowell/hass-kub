"""Knoxville Utilities Board API"""

import copy
from datetime import datetime, timezone
from enum import Enum

import aiohttp


class HTTPError(BaseException):
    """Raised when an HTTP operation fails."""

    def __init__(self, status_code, message) -> None:
        """Raise HTTP Error."""
        self.status_code = status_code
        self.message = message
        super().__init__(self.message, self.status_code)


class KUBAuthenticationError(BaseException):
    """Raised when HTTP login fails."""


class KUBUtilityTypes(Enum):
    """KUB Utility Types"""

    ELECTRICITY = "E"
    GAS = "G"
    WATER = "W"
    WASTEWATER = "WW"


class Http:
    """Simple http class to wrap api calls"""

    def __init__(self) -> None:
        self._session = any

    async def __aenter__(self):
        self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))
        return self

    async def __aexit__(self, *err):
        await self._session.close()
        self._session = None

    async def fetch(self, url):
        """http get"""
        resp = await self._session.get(url)
        resp.raise_for_status()
        return resp

    async def post(self, url, payload):
        """HTTP post"""
        resp = await self._session.post(url, json=payload)
        resp.raise_for_status()
        return resp


class kubUtility:
    """KUB utilities api"""

    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.person_id = ""
        self.account_id = ""
        self.account = {}
        self.usage = {"electricity": {}, "gas": {}, "water": {}}
        self.monthly_total = {"electricity": "", "gas": "", "water": ""}
        self.http = any

    async def retrieve_access_token(self):
        """Retrieve Access Token from KUB api"""
        payload = {}
        session_data = {}
        session_data["username"] = self.username
        session_data["password"] = self.password
        session_data["expirationDate"] = "null"
        session_data["user"] = "null"
        payload["session"] = session_data

        url = "https://www.kub.org/api/auth/v1/sessions"
        response = await self.http.post(url, payload)
        if response.status == 401:
            raise KUBAuthenticationError

    async def retrieve_account_info(self):
        """Retrieve Account Info"""
        response = await self.http.fetch(
            "https://www.kub.org/api/auth/v1/users/" + self.username
        )
        json = await response.json()
        self.person_id = json["person"][0]["id"]
        self.account_id = json["person"][0]["accounts"][0]
        await self._retrieve_services()

    async def _retrieve_services(self):
        url = (
            "https://www.kub.org/api/cis/v1/accounts/"
            + self.account_id
            + "?include=all"
        )
        response = await self.http.fetch(url)
        json = await response.json()
        services = json["service-point"]

        for service in services:
            match service["type"]:
                case "E-RES":
                    self.account["electricity"] = service["id"]
                case "G-RES":
                    self.account["gas"] = service["id"]
                case "W/S-RES":
                    self.account["water"] = service["id"]
                case _:
                    raise Exception("An unexpected service ID:", service["id"])

    async def retrieve_usage(
        self,
        utility_type,
        start_date: str = datetime.today().strftime("%Y-%m-%d"),
        end_date: str = datetime.today().strftime("%Y-%m-%d"),
    ):
        """Retrieve usage by type and date range"""
        # Do we have a valid session?
        await self.retrieve_access_token()

        # Have we retrieved account info?
        if len(self.person_id) == 0:
            await self.retrieve_account_info()

        start_date = datetime.today().replace(day=1).date().strftime("%Y-%m-%d")
        utility = utility_type.name.lower()
        account = self.account[utility]

        url = (
            "https://www.kub.org/api/ami/v1/usage-values"
            + "?endDate="
            + end_date
            + "&personId="
            + self.person_id
            + "&servicePointId="
            + account
            + "&startDate="
            + start_date
            + "&utilityType="
            + utility_type.value
        )

        response = await self.http.fetch(url)
        json = await response.json()
        total = 0.0
        date = ""
        usage_data = {}
        for idx, usage in enumerate(json["usage-value"]):
            if len(usage["usageValuesChildren"]) == 0:
                # Pull data from the base object
                usage_data["id"] = usage["id"]
                usage_data["readDateTime"] = usage["readDateTime"]

                # Grab the usage object via index
                data = json["usage-aggregate"][idx]

                # Read data from the usage object
                usage_data["utilityUsed"] = data["readValue"]
                usage_data["uom"] = data["uom"]
                usage_data["cost"] = data["cost"]

                # Create another object with key of time
                time = datetime.fromisoformat(usage["readDateTime"]).strftime(
                    "%H:%M:%S"
                )
                self.usage[utility][date][time] = {}

                # Apend all the data
                self.usage[utility][date][time] = copy.deepcopy(usage_data)

                total = data["readValue"] + total
                # print(self.usage)
            else:
                # This is the aggregate case so create a new blank object in the list
                date = datetime.fromisoformat(usage["readDateTime"]).strftime(
                    "%Y-%m-%d"
                )
                self.usage[utility][date] = {}

        self.monthly_total[utility] = total
        return self.usage

    async def retrieve_monthly_usage(self):
        """Retrieve all usage for the current month"""
        async with Http() as self.http:
            await self.retrieve_usage(KUBUtilityTypes.ELECTRICITY)
            await self.retrieve_usage(KUBUtilityTypes.GAS)
            await self.retrieve_usage(KUBUtilityTypes.WATER)
        self.http = None
        return self.monthly_total

    async def get_usage_by_datetime(self, usage_record: datetime = datetime.now()):
        """Retrieve usage by datetime"""
        await self.retrieve_monthly_usage()
        elec = (
            self.usage.get("electricity")
            .get(usage_record.today().replace(day=1).date().strftime("%Y-%m-%d"))
            .get(datetime.now(timezone.utc).strftime("%H:00:00"))
        )
        gas = (
            self.usage.get("gas")
            .get(usage_record.today().replace(day=1).date().strftime("%Y-%m-%d"))
            .get(datetime.now(timezone.utc).strftime("%H:00:00"))
        )
        water = (
            self.usage.get("water")
            .get(usage_record.today().replace(day=1).date().strftime("%Y-%m-%d"))
            .get(datetime.now(timezone.utc).strftime("%H:00:00"))
        )
        return elec, gas, water

    async def get_available_services(self):
        """Returns available services for account"""
        if self.account is None:
            async with Http() as self.http:
                await self._retrieve_services()
        return self.account

    async def verify_access(self):
        """Verify username and password is able to retreive api token"""
        async with Http() as self.http:
            await self.retrieve_access_token()
        return self.account
