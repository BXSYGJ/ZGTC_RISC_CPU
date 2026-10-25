"""Bounded transient read retries; callers still require complete raw evidence."""
import time


def read_serial(client, device_id, length, retries, on_error):
    if length not in (16,64,512) or retries not in range(4):
        raise ValueError('Unsupported serial read policy')
    for attempt in range(retries+1):
        try:
            return client.serial_read(device_id,length=length)
        except Exception as error:
            status=getattr(error,'status',None)
            if status not in (502,503,504):
                raise
            will_retry=attempt<retries
            on_error(attempt=attempt+1,status=status,will_retry=will_retry)
            if not will_retry:
                raise
            time.sleep(0.5*(2**attempt))
