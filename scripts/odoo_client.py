import os
import xmlrpc.client
from dotenv import load_dotenv

class OdooClient:
    def __init__(self):
        """
        Initialize the OdooClient by loading environment variables,
        setting up XML-RPC proxies, and authenticating the user.
        """
        load_dotenv()

        # Read configuration values from .env file
        self.url = os.getenv("ODOO_URL")
        self.db = os.getenv("ODOO_DB")
        self.username = os.getenv("ODOO_USER")
        self.password = os.getenv("ODOO_KEY")

        # Initialize XML-RPC proxies
        self.common = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common")
        self.models = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/object")

        # Authenticate and get user ID
        self.uid = self.common.authenticate(self.db, self.username, self.password, {})
        if not self.uid:
            raise Exception("Authentication error: please check your credentials in the .env file.")

    def _jsonrpc(self, service, method, args):
        """
        Internal helper to perform an XML-RPC request.

        :param service: Name of the service ('common', 'object', etc.)
        :param method: Method to call
        :param args: List of arguments to pass
        :return: Result of the RPC call
        """
        proxy = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/{service}")
        return getattr(proxy, method)(*args)

    def search_all_employees(self):
        """
        Search and return all employee record IDs.

        :return: List of employee IDs
        """
        return self._jsonrpc(
            'object', 'execute_kw',
            [self.db, self.uid, self.password, 'hr.employee', 'search', [[]]]
        )

    def read_employees(self, ids, fields):
        """
        Read specified fields from multiple employee records.

        :param ids: List of employee IDs
        :param fields: List of field names to retrieve
        :return: List of dictionaries with employee data
        """
        return self._jsonrpc(
            'object', 'execute_kw',
            [self.db, self.uid, self.password, 'hr.employee', 'read', [ids, fields]]
        )

    def read_employees_in_batches(self, ids, fields, batch_size=25):
        """
        Read employee records in smaller batches to avoid overload.

        :param ids: List of employee IDs
        :param fields: Fields to retrieve
        :param batch_size: Number of records per batch
        :return: Combined list of employee data
        """
        all_data = []
        for i in range(0, len(ids), batch_size):
            batch_ids = ids[i:i + batch_size]
            batch_data = self.read_employees(batch_ids, fields)
            all_data.extend(batch_data)
        return all_data
