"""
Specification of different fictional environments (operating theatres) with devices and clients based on mdib.
"""
import os
import uuid
from colorama import Fore
import time
import random
from threading import Event

from sdc11073 import pmtypes
from sdc11073.definitions_base import ProtocolsRegistry
from sdc11073.definitions_sdc import SDC_v1_Definitions
from sdc11073.location import SdcLocation
from sdc11073.mdib import DeviceMdibContainer
from sdc11073.mdib.clientmdib import ClientMdibContainer
from sdc11073.namespaces import domTag
from sdc11073.pmtypes import CodedValue
from sdc11073.pysoap.soapenvelope import DPWSThisModel, DPWSThisDevice
from sdc11073.roles.product import BaseProduct
from sdc11073.roles.providerbase import ProviderRole
from sdc11073.sdcclient import SdcClient
from sdc11073.sdcdevice.sdcdeviceimpl import SdcDevice
from sdc11073.wsdiscovery import WSDiscoveryWhitelist, WSDiscoverySingleAdapter, Scope


# definition of some configuration variables and paths 
SEARCH_TIMEOUT = 10
current_dir = os.path.dirname(__file__)
mdib_test_path = os.path.join(current_dir, 'mdib_test.xml')
mdib_OPtable_path = os.path.join(current_dir, 'mdib_OPtable.xml')
loopback_adapter = 'Loopback Pseudo-Interface 1' if os.name == 'nt' else 'lo'


def createTestDevice(wsdiscovery_instance, location, mdibPath, role_provider=None):
    # local mdib that will be sent out on the network
    my_mdib = DeviceMdibContainer.fromMdibFile(mdibPath)
    my_uuid = uuid.uuid4()
    dpwsModel = DPWSThisModel(manufacturer='Draeger',
                            manufacturerUrl='www.draeger.com',
                            modelName='TestDevice',
                            modelNumber='1.0',
                            modelUrl='www.draeger.com/model',
                            presentationUrl='www.draeger.com/model/presentation')

    dpwsDevice = DPWSThisDevice(friendlyName='TestDevice',
                                firmwareVersion='Version1',
                                serialNumber='12345')
    sdcDevice = SdcDevice(wsdiscovery_instance,
                        my_uuid,
                        dpwsModel,
                        dpwsDevice,
                        my_mdib,
                        roleProvider=role_provider)
    for desc in sdcDevice.mdib.descriptions.objects:
        desc.SafetyClassification = pmtypes.SafetyClassification.MED_A
    sdcDevice.startAll(startRealtimeSampleLoop=False)
    validators = [pmtypes.InstanceIdentifier('Validator', extensionString='System')]
    sdcDevice.setLocation(location, validators)
    return sdcDevice


def createOPDevice(wsdiscovery_instance, location, mdibPath, role_provider=None):
    my_mdib = DeviceMdibContainer.fromMdibFile(mdibPath)
    my_uuid = uuid.uuid4()
    print(Fore.MAGENTA + "device has UUID: {}".format(my_uuid))
    dpwsModel = DPWSThisModel(manufacturer='Example GmbH',
                            manufacturerUrl='www.exampleGmbH.de',
                            modelName='Example Model',
                            modelNumber='0000',
                            modelUrl='www.exampleGmbH.de/0000',
                            presentationUrl='www.exampleGmbH.de/0000/presentation.pdf')

    dpwsDevice = DPWSThisDevice(friendlyName='Example Model',
                                firmwareVersion='Version1',
                                serialNumber='unknown')
    sdcDevice = SdcDevice(wsdiscovery_instance,
                        my_uuid,
                        dpwsModel,
                        dpwsDevice,
                        my_mdib,
                        roleProvider=role_provider)
    for desc in sdcDevice.mdib.descriptions.objects:
        desc.SafetyClassification = pmtypes.SafetyClassification.MED_A
    sdcDevice.startAll(startRealtimeSampleLoop=False)
    validators = [pmtypes.InstanceIdentifier('Validator', extensionString='System')]
    sdcDevice.setLocation(location, validators)
    return sdcDevice


class Med_Environments():

    def setUp(self) -> None:
        # fac: facility, bld: building, poc: point of care, flr: floor, rm: room, bed: bed 
        self.my_location1 = SdcLocation(fac='ODDS',
                                       bld='A',
                                       poc='CU1',
                                       flr='1',
                                       rm='101',
                                       bed='BedSim1')
        self.my_location2 = SdcLocation(fac='ODDS',
                                        bld='B',
                                        poc='CU2',
                                        flr='2',
                                        rm='12',
                                        bed='BedSim2')
        self.my_devices = []
        self.my_clients = []
        self.my_wsdiscoveries = []

    def tearDown(self) -> None:
        for cl in self.my_clients:
            print('stopping {}'.format(cl))
            cl.stopAll()
        for d in self.my_devices:
            print('stopping {}'.format(d))
            d.stopAll()
        for w in self.my_wsdiscoveries:
            print('stopping {}'.format(w))
            w.stop()  


    def start_test_env(self):
        """ creates fictional environment with one test device that instantiates 2 providers to handle different
        operation calls from a client """

        print(Fore.BLUE + 'starting medical environment with one test device that instantiates 2 providers')

        # use some set and get operations to control the device remotely (defined in mdib under SCO)
        MY_CODE_1 = CodedValue('196279')  # refers to an activate operation (actop.mds0_sco_0 value=foo)
        MY_CODE_2 = CodedValue('196278')  # refers to a set string operation (string.ch0.vmd1_sco_0 requestedString=foo)
        MY_CODE_3 = CodedValue('196276')  # refers to a set value operation (numeric.ch0.vmd1_sco_0 requestedNumericValue=42)
        MY_CODE_3_TARGET = CodedValue('196274')  # this is the operation target for MY_CODE_3 (numeric.ch0.vmd1)

        class MyProvider1(ProviderRole):
            """ This provider handles operations with code == MY_CODE_1 and MY_CODE_2. """

            def __init__(self, log_prefix):
                super().__init__(log_prefix)
                self.operation1_called = 0
                self.operation1_args = None
                self.operation2_called = 0
                self.operation2_args = None

            def makeOperationInstance(self, operationDescriptorContainer):
                """ If the role provider is responsible for handling of calls to this operationDescriptorContainer,
                    it creates an operation instance and returns it. Otherwise it returns None. """
                if operationDescriptorContainer.coding == MY_CODE_1.coding:
                    # This callback is called when a client calls this specific operation
                    operation = self._mkOperationFromOperationDescriptor(operationDescriptorContainer,
                                                                            currentArgumentHandler=self._handle_operation_1)
                    return operation
                elif operationDescriptorContainer.coding == MY_CODE_2.coding:
                    operation = self._mkOperationFromOperationDescriptor(operationDescriptorContainer,
                                                                            currentArgumentHandler=self._handle_operation_2)
                    return operation
                else:
                    return None

            def _handle_operation_1(self, operationInstance, argument):
                """ This operation does not manipulate the mdib at all, it only registers the call. """
                self.operation1_called += 1
                self.operation1_args = argument
                self._logger.info('_handle_operation_1 called')

            def _handle_operation_2(self, operationInstance, argument):
                """ This operation manipulate it operation target (setString), and registers the call. """
                self.operation2_called += 1
                self.operation2_args = argument
                self._logger.info('_handle_operation_2 called')
                with self._mdib.mdibUpdateTransaction() as mgr:
                    my_state = mgr.getMetricState(operationInstance.operationTarget)
                    if my_state.metricValue is None:
                        my_state.mkMetricValue()
                    my_state.metricValue.Value = argument

        class MyProvider2(ProviderRole):
            """ This provider handles operations with code == MY_CODE_3. """

            def __init__(self, log_prefix):
                super().__init__(log_prefix)
                self.operation3_args = None
                self.operation3_called = 0

            def makeOperationInstance(self, operationDescriptorContainer):
                if operationDescriptorContainer.coding == MY_CODE_3.coding:
                    self._logger.info(
                        'instantiating operation 3 from existing descriptor handle={}'.format(
                            operationDescriptorContainer.handle))
                    operation = self._mkOperationFromOperationDescriptor(operationDescriptorContainer,
                                                                            currentArgumentHandler=self._handle_operation_3)
                    return operation
                else:
                    return None

            def _handle_operation_3(self, operationInstance, argument):
                """ This operation manipulate it operation target (setValue), and registers the call. """
                self.operation3_called += 1
                self.operation3_args = argument
                self._logger.info('_handle_operation_3 called')
                with self._mdib.mdibUpdateTransaction() as mgr:
                    # get the state of the metric
                    my_state = mgr.getMetricState(operationInstance.operationTarget)
                    if my_state.metricValue is None:
                        my_state.mkMetricValue()
                    # change the value of the metric
                    my_state.metricValue.Value = argument

        # device with two providers, where each provider handles different operation calls from client
        class MyProductImpl(BaseProduct):

            def __init__(self, log_prefix=None):
                super().__init__(log_prefix)
                self.my_provider_1 = MyProvider1(log_prefix=log_prefix)
                self._ordered_providers.append(self.my_provider_1)
                self.my_provider_2 = MyProvider2(log_prefix=log_prefix)
                self._ordered_providers.append(self.my_provider_2)

        # start device (wsDiscovery is used to publish the device on the network)
        #my_wsDiscovery = WSDiscoveryWhitelist(['127.0.0.1'])
        my_wsDiscovery = WSDiscoverySingleAdapter('Ethernet 2')
        #my_wsDiscovery = WSDiscoverySingleAdapter(loopback_adapter)
        self.my_wsdiscoveries.append(my_wsDiscovery)
        my_wsDiscovery.start()

        my_product_impl = MyProductImpl(log_prefix='p1')

        my_genericDevice = createTestDevice(my_wsDiscovery,
                                                self.my_location,
                                                mdib_test_path,
                                                role_provider=my_product_impl)

        self.my_devices.append(my_genericDevice)

        # connect a client to this device
        #my_client_wsDiscovery = WSDiscoveryWhitelist(['127.0.0.1'])
        my_client_wsDiscovery = WSDiscoverySingleAdapter('Ethernet 2')
        #my_client_wsDiscovery = WSDiscoverySingleAdapter(loopback_adapter)
        self.my_wsdiscoveries.append(my_client_wsDiscovery)
        my_client_wsDiscovery.start()

        # client has to search after services provided by the device
        services = my_client_wsDiscovery.searchServices(timeout=SEARCH_TIMEOUT)
        
        # in this case there is only one medical device on the network, 
        # therefore there is no need to identify to correct one by its uuid
        my_client = SdcClient.fromWsdService(services[0])
        self.my_clients.append(my_client)
        my_client.startAll()
        # variable will contain the data from the provider
        myMdib = ClientMdibContainer(my_client)
        myMdib.initMdib()

        # client calls activate operation
        operations = myMdib.descriptions.coding.get(MY_CODE_1.coding)
        # the mdib contains 2 operations with the same code 
        op = operations[0]
        future = my_client.SetService_client.activate(op.handle, 'foo')
        result = future.result()
        print(result)

        # client calls setString operation
        op = myMdib.descriptions.coding.getOne(MY_CODE_2.coding)
        for value in ('foo', 'bar'):
            future = my_client.SetService_client.setString(op.handle, value)
            result = future.result()
            print(result)
            state = myMdib.states.descriptorHandle.getOne(op.OperationTarget)

        # client calls setValue operation
        state_descr = myMdib.descriptions.coding.getOne(MY_CODE_3_TARGET.coding)
        operations = myMdib.getOperationDescriptorsForDescriptorHandle(state_descr.Handle)
        op = operations[0]
        future = my_client.SetService_client.setNumericValue(op.handle, 42)
        result = future.result()
        print(result)
        state = myMdib.states.descriptorHandle.getOne(op.OperationTarget)
    

    def start_OPtable_env(self, testdata=False):
        """ creates fictional operating theatre with one operating table as device that instantiates 2 providers to handle different
        operation calls from clients (like C-Arm, external controlling-monitor, etc.) """

        print(Fore.BLUE + 'starting operating theatre with an operating table as device')

        # use some operations to control the device remotely (defined in mdib under SCO)
        # operations related to vmd0: operating table column
        act_OPtable = CodedValue('134109') 
        set_lift_pos = CodedValue('134159') 
        set_lift_speed = CodedValue('134156')  
        set_tilt_pos = CodedValue('134155') 
        set_tilt_speed = CodedValue('134153') 
        set_slant_pos = CodedValue('134160')
        set_slant_speed = CodedValue('134146')
        set_column_type = CodedValue('134154')
        set_transporter = CodedValue('134147')
        set_columnLock = CodedValue('134148')

        # operations related to vmd1: operating table surface
        set_slant_pos_surface = CodedValue('134149')
        set_slant_speed_surface = CodedValue('134150')
        set_longitud_pos = CodedValue('134151')
        set_longitud_speed = CodedValue('134152')
        set_transver_pos = CodedValue('134157')
        set_transver_speed = CodedValue('134158')
        set_surface_type = CodedValue('134161')
        set_hinge_module = CodedValue('134162')
        set_installation = CodedValue('134163')

        class Provider_Column(ProviderRole):
            """ Provider that handles operations related to the column of the operating table. """

            def __init__(self, log_prefix):
                super().__init__(log_prefix)
                self.act_OPtable_calls = 0
                self.act_OPtable_args = None
                self.set_lift_pos_calls = 0
                self.set_lift_pos_args = None
                self.set_lift_speed_calls = 0
                self.set_lift_speed_args = None
                self.set_tilt_pos_calls = 0
                self.set_tilt_pos_args = None
                self.set_tilt_speed_calls = 0
                self.set_tilt_speed_args = None
                self.set_slant_pos_calls = 0
                self.set_slant_pos_args = None
                self.set_slant_speed_calls = 0
                self.set_slant_speed_args = None
                self.set_column_type_calls = 0
                self.set_column_type_args = None
                self.set_transporter_calls = 0
                self.set_transporter_args = None
                self.set_columnLock_calls = 0
                self.set_columnLock_args = None

            def makeOperationInstance(self, operationDescriptorContainer):
                if operationDescriptorContainer.coding == act_OPtable.coding:
                    operation = self._mkOperationFromOperationDescriptor(operationDescriptorContainer,
                                                                            currentArgumentHandler=self._handle_act_OPtable)
                    return operation
                elif operationDescriptorContainer.coding == set_lift_pos.coding:
                    operation = self._mkOperationFromOperationDescriptor(operationDescriptorContainer,
                                                                            currentArgumentHandler=self._handle_set_lift_pos)
                    return operation
                elif operationDescriptorContainer.coding == set_lift_speed.coding:
                    operation = self._mkOperationFromOperationDescriptor(operationDescriptorContainer,
                                                                            currentArgumentHandler=self._handle_set_lift_speed)
                    return operation
                elif operationDescriptorContainer.coding == set_tilt_pos.coding:
                    operation = self._mkOperationFromOperationDescriptor(operationDescriptorContainer,
                                                                            currentArgumentHandler=self._handle_set_tilt_pos)
                    return operation
                elif operationDescriptorContainer.coding == set_tilt_speed.coding:
                    operation = self._mkOperationFromOperationDescriptor(operationDescriptorContainer,
                                                                            currentArgumentHandler=self._handle_set_tilt_speed)
                    return operation
                elif operationDescriptorContainer.coding == set_slant_pos.coding:
                    operation = self._mkOperationFromOperationDescriptor(operationDescriptorContainer,
                                                                            currentArgumentHandler=self._handle_set_slant_pos)
                    return operation
                elif operationDescriptorContainer.coding == set_slant_speed.coding:
                    operation = self._mkOperationFromOperationDescriptor(operationDescriptorContainer,
                                                                            currentArgumentHandler=self._handle_set_slant_speed)
                    return operation
                elif operationDescriptorContainer.coding == set_column_type.coding:
                    operation = self._mkOperationFromOperationDescriptor(operationDescriptorContainer,
                                                                            currentArgumentHandler=self._handle_set_column_type)
                    return operation
                elif operationDescriptorContainer.coding == set_transporter.coding:
                    operation = self._mkOperationFromOperationDescriptor(operationDescriptorContainer,
                                                                            currentArgumentHandler=self._handle_set_transporter)
                    return operation
                elif operationDescriptorContainer.coding == set_columnLock.coding:
                    operation = self._mkOperationFromOperationDescriptor(operationDescriptorContainer,
                                                                            currentArgumentHandler=self._handle_set_columnLock)
                    return operation
                else:
                    return None

            def _handle_act_OPtable(self, operationInstance, argument):
                self.act_OPtable_calls += 1
                self.act_OPtable_args = argument
                self._logger.info('_handle_act_OPtable called')
                with self._mdib.mdibUpdateTransaction() as mgr:
                    my_state = mgr.getMetricState(operationInstance.operationTarget)
                    if my_state.metricValue is None:
                        my_state.mkMetricValue()
                    my_state.metricValue.Value = argument
                    print(Fore.YELLOW + f'changed OP-table status to {my_state.metricValue.Value}')
            
            def _handle_set_lift_pos(self, operationInstance, argument):
                self.set_lift_pos_calls += 1
                self.set_lift_pos_args = argument
                self._logger.info('_handle_set_lift_pos called')
                with self._mdib.mdibUpdateTransaction() as mgr:
                    my_state = mgr.getMetricState(operationInstance.operationTarget)
                    if my_state.metricValue is None:
                        my_state.mkMetricValue()
                    my_state.metricValue.Value = argument
                    print(Fore.YELLOW + f'changed lift-position to {my_state.metricValue.Value} mm')

            def _handle_set_lift_speed(self, operationInstance, argument):
                self.set_lift_speed_calls += 1
                self.set_lift_speed_args = argument
                self._logger.info('_handle_set_lift_speed called')
                with self._mdib.mdibUpdateTransaction() as mgr:
                    my_state = mgr.getMetricState(operationInstance.operationTarget)
                    if my_state.metricValue is None:
                        my_state.mkMetricValue()
                    my_state.metricValue.Value = argument
                    print(Fore.YELLOW + f'changed lift-speed to {my_state.metricValue.Value} mm/s')

            def _handle_set_tilt_pos(self, operationInstance, argument):
                self.set_tilt_pos_calls += 1
                self.set_tilt_pos_args = argument
                self._logger.info('_handle_set_tilt_pos called')
                with self._mdib.mdibUpdateTransaction() as mgr:
                    my_state = mgr.getMetricState(operationInstance.operationTarget)
                    if my_state.metricValue is None:
                        my_state.mkMetricValue()
                    my_state.metricValue.Value = argument
                    print(Fore.YELLOW + f'changed tilt-position to {my_state.metricValue.Value} deg')

            def _handle_set_tilt_speed(self, operationInstance, argument):
                self.set_tilt_speed_calls += 1
                self.set_tilt_speed_args = argument
                self._logger.info('_handle_set_tilt_speed called')
                with self._mdib.mdibUpdateTransaction() as mgr:
                    my_state = mgr.getMetricState(operationInstance.operationTarget)
                    if my_state.metricValue is None:
                        my_state.mkMetricValue()
                    my_state.metricValue.Value = argument
                    print(Fore.YELLOW + f'changed tilt-speed to {my_state.metricValue.Value} rad/s')

            def _handle_set_slant_pos(self, operationInstance, argument):
                self.set_slant_pos_calls += 1
                self.set_slant_pos_args = argument
                self._logger.info('_handle_set_slant_pos called')
                with self._mdib.mdibUpdateTransaction() as mgr:
                    my_state = mgr.getMetricState(operationInstance.operationTarget)
                    if my_state.metricValue is None:
                        my_state.mkMetricValue()
                    my_state.metricValue.Value = argument
                    print(Fore.YELLOW + f'changed slant-position to {my_state.metricValue.Value} deg')
            
            def _handle_set_slant_speed(self, operationInstance, argument):
                self.set_slant_speed_calls += 1
                self.set_slant_speed_args = argument
                self._logger.info('_handle_set_slant_speed called')
                with self._mdib.mdibUpdateTransaction() as mgr:
                    my_state = mgr.getMetricState(operationInstance.operationTarget)
                    if my_state.metricValue is None:
                        my_state.mkMetricValue()
                    my_state.metricValue.Value = argument
                    print(Fore.YELLOW + f'changed slant-speed to {my_state.metricValue.Value} rad/s')

            def _handle_set_column_type(self, operationInstance, argument):
                self.set_column_type_calls += 1
                self.set_column_type_args = argument
                self._logger.info('_handle_set_column_type called')
                with self._mdib.mdibUpdateTransaction() as mgr:
                    my_state = mgr.getMetricState(operationInstance.operationTarget)
                    if my_state.metricValue is None:
                        my_state.mkMetricValue()
                    my_state.metricValue.Value = argument
                    print(Fore.YELLOW + f'changed column type to {my_state.metricValue.Value}')

            def _handle_set_transporter(self, operationInstance, argument):
                self.set_transporter_calls += 1
                self.set_transporter_args = argument
                self._logger.info('_handle_set_transporter called')
                with self._mdib.mdibUpdateTransaction() as mgr:
                    my_state = mgr.getMetricState(operationInstance.operationTarget)
                    if my_state.metricValue is None:
                        my_state.mkMetricValue()
                    my_state.metricValue.Value = argument
                    print(Fore.YELLOW + f'changed transporter status to {my_state.metricValue.Value}')

            def _handle_set_columnLock(self, operationInstance, argument):
                self.set_columnLock_calls += 1
                self.set_columnLock_args = argument
                self._logger.info('_handle_set_columnLock called')
                with self._mdib.mdibUpdateTransaction() as mgr:
                    my_state = mgr.getMetricState(operationInstance.operationTarget)
                    if my_state.metricValue is None:
                        my_state.mkMetricValue()
                    my_state.metricValue.Value = argument
                    print(Fore.YELLOW + f'changed column lock status to {my_state.metricValue.Value}')

        class Provider_Surface(ProviderRole):
            """ Provider that handles operations related to the surface of the operating table. """

            def __init__(self, log_prefix):
                super().__init__(log_prefix)
                self.set_slant_pos_surface_calls = 0
                self.set_slant_pos_surface_args = None
                self.set_slant_speed_surface_calls = 0
                self.set_slant_speed_surface_args = None
                self.set_longitud_pos_calls = 0
                self.set_longitud_pos_args = None
                self.set_longitud_speed_calls = 0
                self.set_longitud_speed_args = None
                self.set_transver_pos_calls = 0
                self.set_transver_pos_args = None
                self.set_transver_speed_calls = 0
                self.set_transver_speed_args = None
                self.set_surface_type_calls = 0
                self.set_surface_type_args = None
                self.set_hinge_module_calls = 0
                self.set_hinge_module_args = None
                self.set_installation_calls = 0
                self.set_installation_args = None

            def makeOperationInstance(self, operationDescriptorContainer):
                if operationDescriptorContainer.coding == set_slant_pos_surface.coding:
                    operation = self._mkOperationFromOperationDescriptor(operationDescriptorContainer,
                                                                            currentArgumentHandler=self._handle_set_slant_pos_surface)
                    return operation
                elif operationDescriptorContainer.coding == set_slant_speed_surface.coding:
                    operation = self._mkOperationFromOperationDescriptor(operationDescriptorContainer,
                                                                            currentArgumentHandler=self._handle_set_slant_speed_surface)
                    return operation
                elif operationDescriptorContainer.coding == set_longitud_pos.coding:
                    operation = self._mkOperationFromOperationDescriptor(operationDescriptorContainer,
                                                                            currentArgumentHandler=self._handle_set_longitud_pos)
                    return operation
                elif operationDescriptorContainer.coding == set_longitud_speed.coding:
                    operation = self._mkOperationFromOperationDescriptor(operationDescriptorContainer,
                                                                            currentArgumentHandler=self._handle_set_longitud_speed)
                    return operation
                elif operationDescriptorContainer.coding == set_transver_pos.coding:
                    operation = self._mkOperationFromOperationDescriptor(operationDescriptorContainer,
                                                                            currentArgumentHandler=self._handle_set_transver_pos)
                    return operation
                elif operationDescriptorContainer.coding == set_transver_speed.coding:
                    operation = self._mkOperationFromOperationDescriptor(operationDescriptorContainer,
                                                                            currentArgumentHandler=self._handle_set_transver_speed)
                    return operation
                elif operationDescriptorContainer.coding == set_surface_type.coding:
                    operation = self._mkOperationFromOperationDescriptor(operationDescriptorContainer,
                                                                            currentArgumentHandler=self._handle_set_surface_type)
                    return operation
                elif operationDescriptorContainer.coding == set_hinge_module.coding:
                    operation = self._mkOperationFromOperationDescriptor(operationDescriptorContainer,
                                                                            currentArgumentHandler=self._handle_set_hinge_module)
                    return operation
                elif operationDescriptorContainer.coding == set_installation.coding:
                    operation = self._mkOperationFromOperationDescriptor(operationDescriptorContainer,
                                                                            currentArgumentHandler=self._handle_set_installation)
                    return operation
                else:
                    return None

            def _handle_set_slant_pos_surface(self, operationInstance, argument):
                self.set_slant_pos_surface_calls += 1
                self.set_slant_pos_surface_args = argument
                self._logger.info('_handle_set_slant_pos_surface called')
                with self._mdib.mdibUpdateTransaction() as mgr:
                    my_state = mgr.getMetricState(operationInstance.operationTarget)
                    if my_state.metricValue is None:
                        my_state.mkMetricValue()
                    my_state.metricValue.Value = argument
                    print(Fore.YELLOW + f'changed surface-slant-position to {my_state.metricValue.Value} deg')

            def _handle_set_slant_speed_surface(self, operationInstance, argument):
                self.set_slant_speed_surface_calls += 1
                self.set_slant_speed_surface_args = argument
                self._logger.info('_handle_set_slant_speed_surface called')
                with self._mdib.mdibUpdateTransaction() as mgr:
                    my_state = mgr.getMetricState(operationInstance.operationTarget)
                    if my_state.metricValue is None:
                        my_state.mkMetricValue()
                    my_state.metricValue.Value = argument
                    print(Fore.YELLOW + f'changed surface-slant-speed to {my_state.metricValue.Value} rad/s')

            def _handle_set_longitud_pos(self, operationInstance, argument):
                self.set_longitud_pos_calls += 1
                self.set_longitud_pos_args = argument
                self._logger.info('_handle_set_longitud_pos called')
                with self._mdib.mdibUpdateTransaction() as mgr:
                    my_state = mgr.getMetricState(operationInstance.operationTarget)
                    if my_state.metricValue is None:
                        my_state.mkMetricValue()
                    my_state.metricValue.Value = argument
                    print(Fore.YELLOW + f'changed longitudinal-position to {my_state.metricValue.Value} mm')

            def _handle_set_longitud_speed(self, operationInstance, argument):
                self.set_longitud_speed_calls += 1
                self.set_longitud_speed_args = argument
                self._logger.info('_handle_set_longitud_speed called')
                with self._mdib.mdibUpdateTransaction() as mgr:
                    my_state = mgr.getMetricState(operationInstance.operationTarget)
                    if my_state.metricValue is None:
                        my_state.mkMetricValue()
                    my_state.metricValue.Value = argument
                    print(Fore.YELLOW + f'changed longitudinal-speed to {my_state.metricValue.Value} mm/s')

            def _handle_set_transver_pos(self, operationInstance, argument):
                self.set_transver_pos_calls += 1
                self.set_transver_pos_args = argument
                self._logger.info('_handle_set_transver_pos called')
                with self._mdib.mdibUpdateTransaction() as mgr:
                    my_state = mgr.getMetricState(operationInstance.operationTarget)
                    if my_state.metricValue is None:
                        my_state.mkMetricValue()
                    my_state.metricValue.Value = argument
                    print(Fore.YELLOW + f'changed transversal-position to {my_state.metricValue.Value} mm')

            def _handle_set_transver_speed(self, operationInstance, argument):
                self.set_transver_speed_calls += 1
                self.set_transver_speed_args = argument
                self._logger.info('_handle_set_transver_speed called')
                with self._mdib.mdibUpdateTransaction() as mgr:
                    my_state = mgr.getMetricState(operationInstance.operationTarget)
                    if my_state.metricValue is None:
                        my_state.mkMetricValue()
                    my_state.metricValue.Value = argument
                    print(Fore.YELLOW + f'changed transversal-speed to {my_state.metricValue.Value} mm/s')

            def _handle_set_surface_type(self, operationInstance, argument):
                self.set_surface_type_calls += 1
                self.set_surface_type_args = argument
                self._logger.info('_handle_set_surface_type called')
                with self._mdib.mdibUpdateTransaction() as mgr:
                    my_state = mgr.getMetricState(operationInstance.operationTarget)
                    if my_state.metricValue is None:
                        my_state.mkMetricValue()
                    my_state.metricValue.Value = argument
                    print(Fore.YELLOW + f'changed surface type to {my_state.metricValue.Value}')

            def _handle_set_hinge_module(self, operationInstance, argument):
                self.set_hinge_module_calls += 1
                self.set_hinge_module_args = argument
                self._logger.info('_handle_set_hinge_module called')
                with self._mdib.mdibUpdateTransaction() as mgr:
                    my_state = mgr.getMetricState(operationInstance.operationTarget)
                    if my_state.metricValue is None:
                        my_state.mkMetricValue()
                    my_state.metricValue.Value = argument
                    print(Fore.YELLOW + f'installed new hinge-module {my_state.metricValue.Value}')

            def _handle_set_installation(self, operationInstance, argument):
                self.set_installation_calls += 1
                self.set_installation_args = argument
                self._logger.info('_handle_set_installation called')
                with self._mdib.mdibUpdateTransaction() as mgr:
                    my_state = mgr.getMetricState(operationInstance.operationTarget)
                    if my_state.metricValue is None:
                        my_state.mkMetricValue()
                    my_state.metricValue.Value = argument
                    print(Fore.YELLOW + f'changed installation status of the surface to {my_state.metricValue.Value}')
        
        class Product_OPtable(BaseProduct):

            def __init__(self, log_prefix=None):
                super().__init__(log_prefix)
                self.provider_column = Provider_Column(log_prefix=log_prefix)
                self._ordered_providers.append(self.provider_column)
                self.provider_surface = Provider_Surface(log_prefix=log_prefix)
                self._ordered_providers.append(self.provider_surface)

        if testdata == False:

            start = time.time()

            # start device 
            wsDiscovery_device = WSDiscoverySingleAdapter('Ethernet 2')
            self.my_wsdiscoveries.append(wsDiscovery_device)
            wsDiscovery_device.start()

            OPtable_implement = Product_OPtable(log_prefix='Example Model')

            OPtable_device = createOPDevice(wsDiscovery_device,
                                                    self.my_location1,
                                                    mdib_OPtable_path,
                                                    role_provider=OPtable_implement)

            self.my_devices.append(OPtable_device)

            # connect a client to this device
            wsDiscovery_client = WSDiscoverySingleAdapter('Ethernet 2')
            self.my_wsdiscoveries.append(wsDiscovery_client)
            wsDiscovery_client.start()

            # client has to search after services provided by the medical devices
            services = wsDiscovery_client.searchServices(timeout=SEARCH_TIMEOUT, types=SDC_v1_Definitions.MedicalDeviceTypesFilter)
            print(Fore.MAGENTA + f'client found {len(services)} device[s]')

            # this client could demonstrate sth. like an external console 
            client_1 = SdcClient.fromWsdService(services[0])
            self.my_clients.append(client_1)
            client_1.startAll()
            mdib_client_1 = ClientMdibContainer(client_1)
            mdib_client_1.initMdib()

            # this client could demonstrate an internal interface 
            client_2 = SdcClient.fromWsdService(services[0])
            self.my_clients.append(client_2)
            client_2.startAll()
            mdib_client_2 = ClientMdibContainer(client_2)
            mdib_client_2.initMdib()

            # this client could demonstrate sth. like a c-arm 
            client_3 = SdcClient.fromWsdService(services[0])
            self.my_clients.append(client_3)
            client_3.startAll()
            mdib_client_3 = ClientMdibContainer(client_3)
            mdib_client_3.initMdib()

            # another regular client
            client_4 = SdcClient.fromWsdService(services[0])
            self.my_clients.append(client_4)
            client_4.startAll()
            mdib_client_4 = ClientMdibContainer(client_4)
            mdib_client_4.initMdib()

            # malicious client
            client_5 = SdcClient.fromWsdService(services[0])
            self.my_clients.append(client_5)
            client_5.startAll()
            mdib_client_5 = ClientMdibContainer(client_5)
            mdib_client_5.initMdib()

            # common transactions
            for _ in range(10):
                op = mdib_client_1.descriptions.coding.getOne(set_column_type.coding)
                future = client_1.SetService_client.setString(op.handle, 'stationary')
                result = future.result()
                print(Fore.CYAN + str(result))
                state = mdib_client_1.states.descriptorHandle.getOne(op.OperationTarget)
                #print(Fore.CYAN + str(state))

                op = mdib_client_1.descriptions.coding.getOne(set_transporter.coding)
                future = client_1.SetService_client.setString(op.handle, 'ON')
                result = future.result()
                print(Fore.CYAN + str(result))

                op = mdib_client_1.descriptions.coding.getOne(set_surface_type.coding)
                future = client_1.SetService_client.setString(op.handle, 'Example Surface')
                result = future.result()
                print(Fore.CYAN + str(result))

                op = mdib_client_1.descriptions.coding.getOne(set_transporter.coding)
                future = client_1.SetService_client.setString(op.handle, 'OFF')
                result = future.result()
                print(Fore.CYAN + str(result))

                op = mdib_client_1.descriptions.coding.getOne(set_installation.coding)
                future = client_1.SetService_client.setString(op.handle, 'ON')
                result = future.result()
                print(Fore.CYAN + str(result))

                op = mdib_client_2.descriptions.coding.getOne(set_columnLock.coding)
                future = client_2.SetService_client.setString(op.handle, 'ON')
                result = future.result()
                print(Fore.CYAN + str(result))
                    
                op = mdib_client_2.descriptions.coding.getOne(set_lift_speed.coding)
                future = client_2.SetService_client.setNumericValue(op.handle, round(random.uniform(0.0, 13.2), 4))
                result = future.result()
                print(Fore.CYAN + str(result))

                # retriggerable
                lift_pos_value = round(random.uniform(0.0, 600.0), 4)
                op = mdib_client_2.descriptions.coding.getOne(set_lift_pos.coding)
                for _ in range(5):
                    future = client_2.SetService_client.setNumericValue(op.handle, lift_pos_value)
                    result = future.result()
                    Event().wait(1)
                print(Fore.CYAN + str(result))

                op = mdib_client_3.descriptions.coding.getOne(set_tilt_speed.coding)
                future = client_3.SetService_client.setNumericValue(op.handle, round(random.uniform(0.0, 0.0419), 4))
                result = future.result()
                print(Fore.CYAN + str(result))

                #retriggerable
                tilt_pos_value = round(random.uniform(-25.0, 25.0), 4)
                op = mdib_client_3.descriptions.coding.getOne(set_tilt_pos.coding)
                for _ in range(2):
                    future = client_3.SetService_client.setNumericValue(op.handle, tilt_pos_value)
                    result = future.result()
                    Event().wait(1)
                print(Fore.CYAN + str(result))

                op = mdib_client_3.descriptions.coding.getOne(set_slant_speed.coding)
                future = client_3.SetService_client.setNumericValue(op.handle, round(random.uniform(0.0, 0.0349), 4))
                result = future.result()
                print(Fore.CYAN + str(result))

                # retriggerable
                slant_pos_value = round(random.uniform(-40.0, 40.0), 4)
                op = mdib_client_3.descriptions.coding.getOne(set_slant_pos.coding)
                for _ in range(3):
                    future = client_3.SetService_client.setNumericValue(op.handle, slant_pos_value)
                    result = future.result()
                    Event().wait(1)
                print(Fore.CYAN + str(result))

                op = mdib_client_4.descriptions.coding.getOne(set_slant_speed_surface.coding)
                future = client_4.SetService_client.setNumericValue(op.handle, round(random.uniform(0.0, 0.0349)), 4)
                result = future.result()
                print(Fore.CYAN + str(result))

                # retriggerable
                slant_pos_surface_value = round(random.uniform(-15.0, 15.0), 4)
                op = mdib_client_4.descriptions.coding.getOne(set_slant_pos_surface.coding)
                for _ in range(4):
                    future = client_4.SetService_client.setNumericValue(op.handle, slant_pos_surface_value)
                    result = future.result()
                    Event().wait(1)
                print(Fore.CYAN + str(result))

                op = mdib_client_4.descriptions.coding.getOne(set_longitud_speed.coding)
                future = client_4.SetService_client.setNumericValue(op.handle, round(random.uniform(0.0, 150.0), 4))
                result = future.result()
                print(Fore.CYAN + str(result))

                # retriggerable
                longitud_pos_value = round(random.uniform(0.0, 1000.0), 4)
                op = mdib_client_4.descriptions.coding.getOne(set_longitud_pos.coding)
                for _ in range(3):
                    future = client_4.SetService_client.setNumericValue(op.handle, longitud_pos_value)
                    result = future.result()
                    Event().wait(1)
                print(Fore.CYAN + str(result))

                op = mdib_client_3.descriptions.coding.getOne(set_transver_speed.coding)
                future = client_3.SetService_client.setNumericValue(op.handle, round(random.uniform(0.0, 40.0), 4))
                result = future.result()
                print(Fore.CYAN + str(result))

                # retriggerable
                transver_pos_value = round(random.uniform(-100.0, 100.0), 4)
                op = mdib_client_3.descriptions.coding.getOne(set_transver_pos.coding)
                for _ in range(2):
                    future = client_3.SetService_client.setNumericValue(op.handle, transver_pos_value)
                    result = future.result()
                    Event().wait(1)
                print(Fore.CYAN + str(result))

                # delay to demonstrate some operations executed by the c-arm
                Event().wait(10)

                op = mdib_client_2.descriptions.coding.getOne(set_columnLock.coding)
                future = client_2.SetService_client.setString(op.handle, 'OFF')
                result = future.result()
                print(Fore.CYAN + str(result))

                op = mdib_client_2.descriptions.coding.getOne(set_lift_pos.coding)
                future = client_2.SetService_client.setNumericValue(op.handle, round(random.uniform(0.0, 600.0), 4))
                result = future.result()
                print(Fore.CYAN + str(result))

                # delay to demonstrate some examinations made by the clinical staff
                Event().wait(15)

                op = mdib_client_2.descriptions.coding.getOne(set_lift_speed.coding)
                future = client_2.SetService_client.setNumericValue(op.handle, round(random.uniform(0.0, 13.2), 4))
                result = future.result()
                print(Fore.CYAN + str(result))

                # retriggerable
                lift_pos_value = round(random.uniform(0.0, 600.0), 4)
                op = mdib_client_2.descriptions.coding.getOne(set_lift_pos.coding)
                for _ in range(7):
                    future = client_2.SetService_client.setNumericValue(op.handle, lift_pos_value)
                    result = future.result()
                    Event().wait(1)
                print(Fore.CYAN + str(result))

                op = mdib_client_2.descriptions.coding.getOne(set_columnLock.coding)
                future = client_2.SetService_client.setString(op.handle, 'ON')
                result = future.result()
                print(Fore.CYAN + str(result))

                op = mdib_client_3.descriptions.coding.getOne(set_longitud_speed.coding)
                future = client_3.SetService_client.setNumericValue(op.handle, round(random.uniform(0.0, 150.0), 4))
                result = future.result()
                print(Fore.CYAN + str(result))

                # retriggerable
                longitud_pos_value = round(random.uniform(0.0, 1000.0), 4)
                op = mdib_client_3.descriptions.coding.getOne(set_longitud_pos.coding)
                for _ in range(4):
                    future = client_3.SetService_client.setNumericValue(op.handle, longitud_pos_value)
                    result = future.result()
                    Event().wait(1)
                print(Fore.CYAN + str(result))

                op = mdib_client_3.descriptions.coding.getOne(set_tilt_speed.coding)
                future = client_3.SetService_client.setNumericValue(op.handle, round(random.uniform(0.0, 0.0419), 4))
                result = future.result()
                print(Fore.CYAN + str(result))

                # retriggerable
                tilt_pos_value = round(random.uniform(-25.0, 25.0), 4)
                op = mdib_client_3.descriptions.coding.getOne(set_tilt_pos.coding)
                for _ in range(2):
                    future = client_3.SetService_client.setNumericValue(op.handle, tilt_pos_value)
                    result = future.result()
                    Event().wait(1)
                print(Fore.CYAN + str(result))

                op = mdib_client_4.descriptions.coding.getOne(set_slant_speed_surface.coding)
                future = client_4.SetService_client.setNumericValue(op.handle, round(random.uniform(0.0, 0.0349), 4))
                result = future.result()
                print(Fore.CYAN + str(result))

                # retriggerable
                slant_pos_surface_value = round(random.uniform(-15.0, 15.0), 4)
                op = mdib_client_4.descriptions.coding.getOne(set_slant_pos_surface.coding)
                for _ in range(3):
                    future = client_4.SetService_client.setNumericValue(op.handle, slant_pos_surface_value)
                    result = future.result()
                    Event().wait(1)
                print(Fore.CYAN + str(result))

                op = mdib_client_4.descriptions.coding.getOne(set_slant_speed.coding)
                future = client_4.SetService_client.setNumericValue(op.handle, round(random.uniform(0.0, 0.0349), 4))
                result = future.result()
                print(Fore.CYAN + str(result))

                # retriggerable
                slant_pos_value = round(random.uniform(-40.0, 40.0), 4)
                op = mdib_client_4.descriptions.coding.getOne(set_slant_pos.coding)
                for _ in range(4):
                    future = client_4.SetService_client.setNumericValue(op.handle, slant_pos_value)
                    result = future.result()
                    Event().wait(1)
                print(Fore.CYAN + str(result))

                op = mdib_client_3.descriptions.coding.getOne(set_transver_speed.coding)
                future = client_3.SetService_client.setNumericValue(op.handle, round(random.uniform(0.0, 40.0), 4))
                result = future.result()
                print(Fore.CYAN + str(result))

                # retriggerable
                transver_pos_value = round(random.uniform(-100.0, 100.0), 4)
                op = mdib_client_3.descriptions.coding.getOne(set_transver_pos.coding)
                for _ in range(6):
                    future = client_3.SetService_client.setNumericValue(op.handle, transver_pos_value)
                    result = future.result()
                    Event().wait(1)
                print(Fore.CYAN + str(result))

            print(Fore.MAGENTA + 'starting the DoS attack...')

            ############################################################################################################
            # simulation of a DoS attack by client5
            ############################################################################################################

            op = mdib_client_2.descriptions.coding.getOne(set_columnLock.coding)
            future = client_2.SetService_client.setString(op.handle, 'ON')
            result = future.result()
            print(Fore.CYAN + str(result))
                
            op = mdib_client_5.descriptions.coding.getOne(set_lift_speed.coding)
            for _ in range(20):
                future = client_5.SetService_client.setNumericValue(op.handle, round(random.uniform(0.0, 13.2), 4))
                result = future.result()
            print(Fore.CYAN + str(result))

            # retriggerable
            op = mdib_client_5.descriptions.coding.getOne(set_lift_pos.coding)
            for _ in range(10):
                future = client_5.SetService_client.setNumericValue(op.handle, round(random.uniform(0.0, 600.0), 4))
                result = future.result()
            print(Fore.CYAN + str(result))

            op = mdib_client_5.descriptions.coding.getOne(set_tilt_speed.coding)
            for _ in range(30):
                future = client_5.SetService_client.setNumericValue(op.handle, round(random.uniform(0.0, 0.0419), 4))
                result = future.result()
            print(Fore.CYAN + str(result))

            # retriggerable
            op = mdib_client_5.descriptions.coding.getOne(set_tilt_pos.coding)
            for _ in range(20):
                future = client_5.SetService_client.setNumericValue(op.handle, round(random.uniform(-25.0, 25.0), 4))
                result = future.result()
            print(Fore.CYAN + str(result))

            op = mdib_client_5.descriptions.coding.getOne(set_slant_speed.coding)
            for _ in range(40):
                future = client_5.SetService_client.setNumericValue(op.handle, round(random.uniform(0.0, 0.0349), 4))
                result = future.result()
            print(Fore.CYAN + str(result))

            # retriggerable
            op = mdib_client_5.descriptions.coding.getOne(set_slant_pos.coding)
            for _ in range(25):
                future = client_5.SetService_client.setNumericValue(op.handle, round(random.uniform(-40.0, 40.0), 4))
                result = future.result()
            print(Fore.CYAN + str(result))

            op = mdib_client_5.descriptions.coding.getOne(set_slant_speed_surface.coding)
            for _ in range(15):
                future = client_5.SetService_client.setNumericValue(op.handle, round(random.uniform(0.0, 0.0349)), 4)
                result = future.result()
            print(Fore.CYAN + str(result))

            # retriggerable
            op = mdib_client_5.descriptions.coding.getOne(set_slant_pos_surface.coding)
            for _ in range(20):
                future = client_5.SetService_client.setNumericValue(op.handle, round(random.uniform(-15.0, 15.0), 4))
                result = future.result()
            print(Fore.CYAN + str(result))

            op = mdib_client_4.descriptions.coding.getOne(set_longitud_speed.coding)
            future = client_4.SetService_client.setNumericValue(op.handle, round(random.uniform(0.0, 150.0), 4))
            result = future.result()
            print(Fore.CYAN + str(result))

            # retriggerable
            longitud_pos_value = round(random.uniform(0.0, 1000.0), 4)
            op = mdib_client_4.descriptions.coding.getOne(set_longitud_pos.coding)
            for _ in range(3):
                future = client_4.SetService_client.setNumericValue(op.handle, longitud_pos_value)
                result = future.result()
                Event().wait(1)
            print(Fore.CYAN + str(result))

            op = mdib_client_5.descriptions.coding.getOne(set_transver_speed.coding)
            for _ in range(40):
                future = client_5.SetService_client.setNumericValue(op.handle, round(random.uniform(0.0, 40.0), 4))
                result = future.result()
            print(Fore.CYAN + str(result))

            # retriggerable
            op = mdib_client_5.descriptions.coding.getOne(set_transver_pos.coding)
            for _ in range(30):
                future = client_5.SetService_client.setNumericValue(op.handle, round(random.uniform(-100.0, 100.0), 4))
                result = future.result()
            print(Fore.CYAN + str(result))

            end = time.time()

            print(Fore.MAGENTA + f'operations took {end - start} seconds to finish')

        #TODO: define environment with security breaches (test dataset)
        # DoS attack: huge amount of sequential requests from a client to one and the same device
        # man-in-the-middle: create inter-packet delays
        # abnormal controlling behavior: like setting lift-speed out of range, etc.
        elif testdata == True:
            pass