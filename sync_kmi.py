import os
import requests

from tablemanager.models import Publish,Workspace
from wmsmanager.models import WmsLayer
from livelayermanager.models import Layer,SqlViewLayer,Datasource,WmsServer
from layergroup.models import LayerGroup

def list_borg_layers():
    all_layers={"features":{},"wmslayers":{},"livelayers":{},"layergroups":{}}
    layers=all_layers["features"]
    for p in Publish.objects.filter(status="Enabled",completed_gt=0):
        workspacename = p.workspace.name
        storename = "{}_ds".format(p.workspace.name)
        layers[workspacename] = layers.get(workspacename) or {}
        layers[workspacename][storename] = layers[workspacename].get(storename) or []
        layers[workspacename][storename].append(p.name)


    layers=all_layers["wmslayers"]
    for l in WmsLayer.objects.filter(status__in=['Updated', 'Published', 'CascadePublished']):
        workspacename = l.server.workspace.name
        storename = l.server.name
        layers[workspacename] = layers.get(workspacename) or {}
        layers[workspacename][storename] = layers[workspacename].get(storename) or []
        layers[workspacename][storename].append(l.kmi_name or l.name)

    layers=all_layers["livelayers"]
    for l in Layer.objects.filter(status__in=['Updated', 'Published', 'CascadePublished']):
        workspacename = l.datasource.workspace.name
        storename = l.datasource.name
        layers[workspacename] = layers.get(workspacename) or {}
        layers[workspacename][storename] = layers[workspacename].get(storename) or []
        layers[workspacename][storename].append(l.name)

    for l in SqlViewLayer.objects.filter(status__in=['Updated', 'Published', 'CascadePublished']):
        workspacename = l.datasource.workspace.name
        storename = l.datasource.name
        layers[workspacename] = layers.get(workspacename) or {}
        layers[workspacename][storename] = layers[workspacename].get(storename) or []
        layers[workspacename][storename].append(l.name)
    """    
    layers=all_layers["layergroups"]
    for l in LayerGroup.objects.filter(status__in=['Updated', 'Published', 'CascadePublished']):
        workspacename = l.workspace.name
        layers[workspacename] = layers.get(workspacename) or []
        layers[workspacename].append(l.name)
    """


    return all_layers

geoserver = os.environ.get('GEOSERVER')
user = os.environ.get('GEOSERVER_USER')
password = os.environ.get('GEOSERVER_password')
def list_kmi_layers():
    all_layers={"features":{},"wmslayers":{},"livelayers":{},"layergroups":{}}

    res = requests.get("{}/geoserver/rest/workspaces.json".format(geoserver),auth=(user, password))
    res.raise_for_status()
    workspaces = res.json()
    for w in workspaces.get("workspaces",{}).get("workspace",[]):
        workspacename = w["name"]
        res = requests.get(w["href"],auth=(user, password))
        res.raise_for_status()
        workspace = res.json()

        res = requests.get(workspace["dataStores"],auth=(user, password))
        res.raise_for_status()
        datastores = res.json()
        for s in datastores.get("dataStores",{}).get("dataStore",[]):
            storename = s["name"]

            res = requests.get(s["href"],auth=(user, password))
            res.raise_for_status()
            store = res.json()

            res = requests.get(store["featureTypes"],auth=(user, password))
            res.raise_for_status()
            features = res.json()

            for f in features.get("featureTypes",{}).get("featureType",[]):
                layername = f["name"]
                layerurl = f["href"]

                all_layers["features"][workspacename] = layers.get(workspacename) or {}
                all_layers["features"][workspacename][storename] = layers[workspacename].get(storename) or []
                all_layers["features"][workspacename][storename].append(layername)

        res = requests.get(workspace["wmsStores"],auth=(user, password))
        res.raise_for_status()
        wmsstores = res.json()
        for s in wmsstores.get("wmsStores",{}).get("wmsStore",[]):
            storename = s["name"]
            
            res = requests.get(s["href"],auth=(user, password))
            res.raise_for_status()
            store = res.json()

            store_capabilitiesurl = store["capabilitiesURL"]
            store_user = store.get("user")
            store_password = store.get("password")

            res = requests.get(store["wmsLayers"],auth=(user, password))
            res.raise_for_status()
            layers = res.json()
            for  l in layers.get("wmsLayers",{}).get("wmsLayer",[]):
                layername = l["name"]
                layerurl = l["href"]
                all_layers["wmslayers"][workspacename] = layers.get(workspacename) or {}
                all_layers["wmslayers"][workspacename][storename] = layers[workspacename].get(storename) or []
                all_layers["wmslayers"][workspacename][storename].append(layername)

    return all_layers


def sync(dry_run=False):
    borg_layers = list_borg_layers()
    kmi_layers = list_kmi_layers()

    stores_not_in_kmi = []
    layers_not_in_kmi = []
    for t,data in borg_layers.items():
        kmi_data = kmi_layers.get(t) or {}
        for workspace,w_data in data.items():
            kmi_w_data = kmi_data.get(workspace) or {}
            for store,layers in w_data.items():
                if store not in kmi_w_data:
                    stores_not_in_kmi.append((t,workspace,store))
                kmi_layers = kmi_w_data.get(store) or []
                for layer in layers:
                    if layer not in kmi_layers:
                        layers_not_in_kmi.append((t,workspace,store,layer))


    stores_not_in_borg = []
    layers_not_in_borg = []
    for t,data in kmi_layers.items():
        borg_data = borg_layers.get(t) or {}
        for workspace,w_data in data.items():
            borg_w_data = borg_data.get(workspace) or {}
            for store,layers in w_data.items():
                if store not in borg_w_data:
                    stores_not_in_borg.append((t,workspace,store))
                borg_layers = borg_w_data.get(store) or []
                for layer in layers:
                    if layer not in borg_layers:
                        layers_not_in_borg.append((t,workspace,store,layer))


    if stores_not_in_kmi:
        print("The stores({}) are published in borg, but not exist in kmi".format(stores_not_in_kmi))

    if layers_not_in_kmi:
        print("The layers({}) are published in borg, but not exist in kmi".format(layers_not_in_kmi))


    if stores_not_in_borg:
        print("The stores({}) doesn't exist in borg, but exist in kmi".format(stores_not_in_borg))

    if layers_not_in_borg:
        print("The layers({}) doesn't exist in borg, but exist in kmi".format(layers_not_in_borg))

    if dry_run:
        return

    for l in layers_not_in_borg:
        print("Try to remove layer({}) from geoserver".format(l))
        if dry_run:
            print("Submit the delete request to delete the layer from geoserver: {0}/workspaces/{1}/wmsstores/{2}/wmslayers/{3}.xml?recurse=true".format(geoserver,l[1],l[2],l[3]))
        else:
            try:
                res = requests.delete("{0}/workspaces/{1}/wmsstores/{2}/wmslayers/{3}.xml?recurse=true".format(geoserver,l[1],l[2],l[3]),auth=(user, password))
                res.raise_for_status()
                print("Succeed to remove layer({}) from geoserver.{}".format(l))
            except Exception as ex:
                print("Failed to remove layer({}) from geoserver.{}".format(l,ex))


    for s in stores_not_in_borg:
        print("Try to remove store({}) from geoserver".format(s))
        if dry_run:
            print("Submit the delete request to delete the layer from geoserver: {0}/workspaces/{1}/wmsstores/{2}.xml".format(geoserver,s[1],s[2]))
        else:
            try:
                res = requests.delete("{0}/workspaces/{1}/wmsstores/{2}.xml".format(geoserver,s[1],s[2]),auth=(user, password))
                res.raise_for_status()
                print("Succeed to remove store({}) from geoserver.{}".format(s))
            except Exception as ex:
                print("Failed to remove store({}) from geoserver.{}".format(s,ex))

