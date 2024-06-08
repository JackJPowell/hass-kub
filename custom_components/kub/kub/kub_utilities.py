"""Knoxville Utilities Board API"""

import copy
from datetime import datetime, timedelta, timezone
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


class KubUtility:
    """KUB utilities api"""

    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.person_id = ""
        self.account_id = ""

        self.account = {}
        self.session_start = ""
        self.usage = {"electricity": {}, "gas": {}, "water": {}, "wastewater": {}}
        self.monthly_total = {
            "electricity": {"usage": None, "cost": None},
            "gas": {"usage": None, "cost": None},
            "water": {"usage": None, "cost": None},
            "wastewater": {"usage": None, "cost": None},
        }
        self.services = {}
        self.service_list = []
        self.http = None

    @property
    def is_session_active(self):
        """Getter that returns if session was created within 15m"""
        if datetime.now() < datetime.now() - timedelta(minutes=15):
            return True
        return False

    async def _retrieve_access_token(self):
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
        self.session_start = datetime.now()

    async def _retrieve_account_info(self):
        """Retrieve Account Info"""
        if self.account_id == "":
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
        self.services = json["service-point"]

        for service in self.services:
            match service["type"]:
                case "E-RES":
                    self.account["electricity"] = service["id"]
                    self.service_list.append(KUBUtilityTypes.ELECTRICITY)
                case "G-RES":
                    self.account["gas"] = service["id"]
                    self.service_list.append(KUBUtilityTypes.GAS)
                case "W/S-RES":
                    self.account["water"] = service["id"]
                    self.account["wastewater"] = service["id"]
                    self.service_list.append(KUBUtilityTypes.WATER)
                    self.service_list.append(KUBUtilityTypes.WASTEWATER)
                case _:
                    raise Exception("An unexpected service ID:", service["id"])
        return self.services

    async def retrieve_account_info(self):
        """Retrieves account info from KUB api"""
        async with Http() as self.http:
            await self._retrieve_access_token()
            await self._retrieve_account_info()

    async def retrieve_access_token(self):
        """Fetches access token"""
        async with Http() as self.http:
            await self._retrieve_access_token()

    async def _retrieve_usage(
        self,
        utility_type,
        start_date: str = datetime.today().strftime("%Y-%m-%d"),
        end_date: str = datetime.today().strftime("%Y-%m-%d"),
    ):
        utility = utility_type.name.lower()
        account = self.account[utility]

        # If we are processing wastewater so just copy water
        # This does not account for separate meters for water and wastewater
        # However, I do not know what the response looks like to process
        # this case properly
        if utility_type == KUBUtilityTypes.WASTEWATER:
            water = KUBUtilityTypes.WATER.name.lower()
            self.usage[utility] = copy.deepcopy(self.usage[water])
            self.monthly_total[utility]["usage"] = self.monthly_total[water]["usage"]
            self.monthly_total[utility]["cost"] = self.monthly_total[water]["cost"]
            return self.usage

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
        total_cost = 0.0
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

                if (
                    datetime.fromisoformat(usage["readDateTime"]).month
                    == datetime.now().month
                ):
                    total = data["readValue"] + total
                    total_cost = data["cost"] + total_cost
                # print(self.usage)
            else:
                # This is the aggregate case so create a new blank object in the list
                date = datetime.fromisoformat(usage["readDateTime"]).strftime(
                    "%Y-%m-%d"
                )
                self.usage[utility][date] = {}

        self.monthly_total[utility]["usage"] = total
        self.monthly_total[utility]["cost"] = total_cost
        return self.usage

    async def retrieve_last_31_days(self):
        """Retrieve all usage for the current month"""
        date = datetime.today() - timedelta(days=31)
        start_date = date.strftime("%Y-%m-%d")

        async with Http() as self.http:
            await self._retrieve_access_token()

            if len(self.person_id) == 0:
                await self._retrieve_account_info()

            for service in self.service_list:
                await self._retrieve_usage(service, start_date=start_date)
        return self.usage

    async def retrieve_monthly_usage(self):
        """Retrieve all usage for the current month"""
        date = datetime.today().replace(day=1).date().strftime("%Y-%m-%d")
        start_date = date.strftime("%Y-%m-%d")

        async with Http() as self.http:
            await self._retrieve_access_token()

            if len(self.person_id) == 0:
                await self._retrieve_account_info()
            for service in self.service_list:
                await self._retrieve_usage(service, start_date=start_date)
        self.http = None
        return self.usage

    async def retrieve_usage_by_range(
        self,
        start_date: str = datetime.today().strftime("%Y-%m-%d"),
        end_date: str = datetime.today().strftime("%Y-%m-%d"),
    ):
        """Retrieve all usage for the current month"""
        async with Http() as self.http:
            await self._retrieve_access_token()

            if len(self.person_id) == 0:
                await self._retrieve_account_info()
            for service in self.service_list:
                await self._retrieve_usage(
                    service, start_date=start_date, end_date=end_date
                )
        self.http = None
        return self.usage

    async def retrieve_monthly_summary(self):
        """Retrieve summary of usage for the current month"""

        start_date = datetime.today().replace(day=1).date().strftime("%Y-%m-%d")

        async with Http() as self.http:
            await self._retrieve_access_token()

            if len(self.person_id) == 0:
                await self._retrieve_account_info()
            for service in self.service_list:
                await self._retrieve_usage(service, start_date=start_date)
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
        async with Http() as self.http:
            await self._retrieve_access_token()

            if len(self.person_id) == 0:
                await self._retrieve_account_info()
        return self.services

    async def verify_access(self):
        """Verify username and password is able to retreive api token"""
        async with Http() as self.http:
            await self._retrieve_access_token()
