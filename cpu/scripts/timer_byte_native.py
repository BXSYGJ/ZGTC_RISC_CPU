import hashlib
import re


def inspect_timer_byte_boundaries(native):
    records=[]
    for byte_index in range(8):
        for relation in ('equal','greater'):
            signal='timer_byte_'+relation+'['+str(byte_index)+']'
            drivers=re.findall(r'GTP_LUT6CARRY\s+[^;]*\.COUT\s*\('+re.escape(signal)+r'\)[^;]*;',native)
            consumers=re.findall(r'\.I[0-5]\s*\('+re.escape(signal)+r'\)',native)
            if len(drivers)!=1 or not consumers:
                raise ValueError('Missing active timer byte boundary: '+signal)
            driver=drivers[0]
            for port in range(4):
                source=('timer_compare' if port%2==0 else 'timer_value') if relation=='equal' else ('timer_value' if port%2==0 else 'timer_compare')
                expected=source+'['+str(byte_index*8+6+port//2)+']'
                if re.findall(r'\.I'+str(port)+r'\s*\(([^)]+)\)',driver)!=[expected]:
                    raise ValueError('Timer byte high-bit mapping changed: '+signal)
            records.append(dict(signal=signal,driver_sha256=hashlib.sha256(driver.encode()).hexdigest().upper(),consumers=len(consumers)))
    return records
