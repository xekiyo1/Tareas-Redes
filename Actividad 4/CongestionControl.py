
from slidingWindowCC import SlidingWindowCC
from socketUDP import SocketUDP
import select


#parte 1
class CongestionControl:
    SLOW_START = "slow_start"
    CONGESTION_AVOIDANCE = "congestion_avoidance"
    
    def __init__(self, MSS:int):
        self.MSS = MSS
        self.cwnd = 1 * MSS #Congestión inicial
        self.ssthresh = None
        self.current_state = self.SLOW_START #Estado inicial
        
        
    def get_cwnd(self):
        return self.cwnd
    
    def get_MSS_in_cwnd(self):
        return int(self.cwnd/self.MSS)
    
    def event_ack_received(self):
        if self.current_state == self.SLOW_START:
            self.cwnd += self.MSS
            
            if self.ssthresh is not None and self.cwnd >= self.ssthresh:
                self.current_state = self.CONGESTION_AVOIDANCE #Cambiar a Congestion Avoidance
                
        elif self.current_state == self.CONGESTION_AVOIDANCE:
            self.cwnd += self.MSS/ self.get_MSS_in_cwnd() #Incremento
            
    
    def event_timeout(self):
        self.ssthresh = self.cwnd//2
        self.cwnd = 1 * self.MSS
        self.current_state = self.SLOW_START
        
        
    def is_state_slow_start(self):
        return self.current_state == self.SLOW_START
    
    def is_state_congestion_avoidance(self):
        return self.current_state == self.CONGESTION_AVOIDANCE
    
    def get_ssthresh(self):
        return self.ssthresh
    
    
    

class SocketTCP:
    
    #implementación actividad 4 parte 2-2
    def __init__(self, seq:int, ack:int, destination_address:tuple[str,int], buff_size:int, MSS:int):
        self.seq = seq
        self.ack = ack
        self.destination_address = destination_address
        self.buff_size = buff_size
        self.MSS = MSS
        self.socketUDP = SocketUDP()
        self.congestion_control_on = False
        self.debug = False
        self.timeout=1.0
        self.number_of_sent_segments=0
        
    
    def set_congestion_control_on(self, value: bool):
        self.congestion_control_on = value
    def set_debug(self, value: bool):
        self.debug = value
            
        
        
        
    def send(self, message, mode="stop_and_wait"):
        if mode == "stop_and_wait":
            return self.send_using_stop_and_wait(message)
        elif mode == "go_back_n":
            return self.send_using_go_back_n(message)
        
    def recv(self, buff_size, mode="stop_and_wait"):
        if mode == "stop_and_wait":
            return self.recv_using_stop_and_wait(buff_size)
        elif mode == "go_back_n":
            return self.recv_using_go_back_n(buff_size)
        
    def send_using_go_back_n(self, message: bytes):
        MSS=8
        WINDOW_SIZE = 8
        self.socketUDP.settimeout(self.timeout)
        self.socketUDP.set_timer_list_length(1)
        
        #paso 1-3
        congestion_controler = CongestionControl(MSS)
        data_list = [str(len(message)).encode()] + [message[i:i+MSS] for i in range(0, len(message), MSS)]
        
        initial_seq = self.seq
        
        
        #paso 4
        if self.congestion_control_on:
            window_size = congestion_controler.get_MSS_in_cwnd()
        else:
            window_size = WINDOW_SIZE
        data_window = SlidingWindowCC(window_size, data_list, initial_seq)
        
        next_seq_to_send = initial_seq
        
        def log(event=""):
            if self.debug:
                print(f"[CC] {event:<16} | {congestion_controler.current_state:<20} "
                    f"cwnd={congestion_controler.get_cwnd():7.2f} "
                    f"ssthresh={congestion_controler.get_ssthresh()} "
                    f"window_size={data_window.window_size}")
                
        
        def send_at(i)->bool:
            data = data_window.get_data(i)
            if data is None:
                return False
            
            seg=self.wrap_data_as_segment(data, data_window.get_sequence_number(i))
            self.socketUDP.sendto(seg, self.destination_address, timer_index=0)
            self.number_of_sent_segments+=1
            return True
        
        def send_new_window():
            nonlocal next_seq_to_send
            sent = False
            for i in range(data_window.window_size):
                seq = data_window.get_sequence_number(i)
                
                if seq is None:
                    break
                if seq >= next_seq_to_send:
                    send_at(i)
                    next_seq_to_send = seq + len(data_window.get_data(i))
                    sent = True
            return sent
        
        
        
        def resend_window():
            nonlocal next_seq_to_send
            self.socketUDP.stop_timer(0)
            next_seq_to_send = data_window.get_sequence_number(0)
            send_new_window()
                
                
                
        def count_acked(ack_seq:int)->int:
            steps=0 
            
            for i in range(data_window.window_size):
                data = data_window.get_data(i)
                if data is None:
                    break
                if data_window.get_sequence_number(i) + len(data) > ack_seq:
                    break
                steps += 1
            return steps
        
        #parte 6
        def update_window_size():
            if self.congestion_control_on:
                new_window_size = congestion_controler.get_MSS_in_cwnd()
                data_window.update_window_size(new_window_size)
                
                
                
        def packet_available()->bool:
            sock = self.socketUDP.socket_udp
            return bool(select.select([sock], [], [], 0.0)[0])
        
        
        log("inicio")
        
        send_new_window()
        
        
            
        while data_window.get_data(0) is not None:
            if 0 in self.socketUDP.get_stopped_timers():
                if self.congestion_control_on:
                    congestion_controler.event_timeout()
                    update_window_size()
                log("Timeout occurred")
                resend_window()
            
            elif packet_available():
                answer, _ = self.socketUDP.socket_udp.recvfrom(self.buff_size)
                ack_seq = self.parse_segment(answer)["ACK"]
                steps= count_acked(self.parse_segment(answer)["ACK"])
                
                if steps>0:
                    self.socketUDP.stop_timer(0)
                    if self.congestion_control_on:
                        congestion_controler.event_ack_received()
                        
                        
                    while steps>0:
                        data_window.move_window(steps)
                        steps = count_acked(ack_seq)
                        
                    base_seq = data_window.get_sequence_number(0)
                    
                    if base_seq is not None:
                        next_seq_to_send = max(next_seq_to_send, base_seq)
                    update_window_size()
                    send_new=send_new_window()
                    
                
                    if not send_new and data_window.get_data(0) is not None:
                        send_at(0)
                    log(f"Received ACK for seq {ack_seq}")
                    
                    
        self.seq = initial_seq + sum([len(d) for d in data_list])
        
        if self.socketUDP.timer_list[0] is not None:
            self.socketUDP.stop_timer(0)
        
    def recv_using_go_back_n(self, buff_size: int):
        expected_seq = self.ack
        message_length = None
        message = b""
        
        def send_ack(seq):
            self.socketUDP.sendto(self.wrap_ack_as_segment(seq), self.destination_address)
            
            if self.socketUDP.timer_list[0] is not None:
                self.socketUDP.stop_timer(0)
                
        while message_length is None or len(message) < message_length:
            segment, _ = self.socketUDP.recvfrom(self.buff_size)
            parsed = self.parse_segment(segment)
            seq = parsed["SEQ"]
            
            if seq == expected_seq:
                if message_length is None:
                    message_length = int(parsed["DATA"])
                else:
                    message += parsed["DATA"]
                
                expected_seq += len(parsed["DATA"])
                
            send_ack(expected_seq)
        self.ack = expected_seq
        return message
    


