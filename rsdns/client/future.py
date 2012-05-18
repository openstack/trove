
class RsDnsError(RuntimeError):

    def __init__(self, error):
        self.error_msg = ""
        try:
            for message in error['validationErrors']['messages']:
                self.error_msg += message
        except KeyError:
            self.error_msg += "... (did not understand the RsDNS response)."
        super(RsDnsError, self).__init__(self.error_msg)

    def __str__(self):
        return self.message

class FutureResource(object):
    """Polls a callback url to return a resource."""
    
    def __init__(self, manager, jobId, callbackUrl, status, **kwargs):
        self.manager = manager
        self.jobId = jobId
        self.callbackUrl = unicode(callbackUrl)
        self.result = None
        management_url = unicode(self.manager.api.client.management_url)
        if self.callbackUrl.startswith(management_url):
            self.callbackUrl = self.callbackUrl[len(management_url):]

    def call_callback(self):
        return self.manager.api.client.get(self.callbackUrl +
                                           "?showDetails=true")

    def poll(self):
        if not self.result:
            resp, body = self.call_callback()
            if resp.status == 202:
                return None
            if resp.status == 200:
                if body['status'] == 'ERROR':
                    raise RsDnsError(body['error'])
                elif body['status'] != 'COMPLETED':
                    return None
                resp_list = body['response'][self.response_list_name()]
                self.result = self.manager.create_from_list(resp_list)
                #self.resource_class(self, res) for res in list]
                #self.result = Domain(self.manager, body['self.convert_callback(resp, body)
        return self.result

    @property
    def ready(self):
        return (self.result or self.poll()) is not None

    @property
    def resource(self):
        return self.result or self.poll()
