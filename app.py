from flask import Flask, request, jsonify, render_template_string
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta

app = Flask(__name__)

# Cấu hình Database SQLite
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///robot_data.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Khởi tạo bảng nếu chưa có
with app.app_context():
    db.create_all()

class DeviceLocation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    device_name = db.Column(db.String(50), nullable=False, default="Android_App")
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    battery = db.Column(db.Integer, nullable=False)
    network = db.Column(db.String(50), nullable=True, default="Không rõ")
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

@app.route('/update_phone', methods=['POST'])
def update_phone():
    try:
        data = request.get_json(force=True)
        if not data:
            return jsonify({"error": "No data"}), 400

        # LƯU VỊ TRÍ MỚI VÀO LỊCH SỬ
        new_location = DeviceLocation(
            device_name=data.get('device_name', 'Thiết bị ẩn danh'),
            latitude=float(data.get('lat', 0.0)),
            longitude=float(data.get('lng', 0.0)),
            battery=int(data.get('battery', 0)),
            network=data.get('network', 'Không rõ')
        )
        db.session.add(new_location)
        
        # 🔥 THUẬT TOÁN CHỐNG TRÀN BỘ NHỚ: Xóa sạch dữ liệu cũ hơn 24 giờ
        twenty_four_hours_ago = datetime.utcnow() - timedelta(days=1)
        DeviceLocation.query.filter(DeviceLocation.timestamp < twenty_four_hours_ago).delete()
        
        db.session.commit()
        return jsonify({"status": "success"}), 200
    except Exception as e:
        print("Lỗi:", e)
        return jsonify({"error": str(e)}), 400

@app.route('/get_phone', methods=['GET'])
def get_phone():
    # Lấy toàn bộ dữ liệu trong 24h qua, sắp xếp từ cũ tới mới để nối thành đường đi
    yesterday = datetime.utcnow() - timedelta(days=1)
    records = DeviceLocation.query.filter(DeviceLocation.timestamp >= yesterday).order_by(DeviceLocation.timestamp.asc()).all()
    
    devices_data = {}
    
    # Gom nhóm dữ liệu theo từng thiết bị
    for r in records:
        name = r.device_name
        if name not in devices_data:
            devices_data[name] = {
                "device_name": name,
                "path": [], # Mảng lưu các vết tọa độ
                "latest": None # Tọa độ cuối cùng
            }
        devices_data[name]["path"].append([r.latitude, r.longitude])
        devices_data[name]["latest"] = r

    result = []
    # Chỉ lấy TỐI ĐA 2 THIẾT BỊ để trả về web
    for name, data in list(devices_data.items())[:2]:
        latest = data["latest"]
        vn_time = latest.timestamp + timedelta(hours=7)
        time_diff = (datetime.utcnow() - latest.timestamp).total_seconds()
        is_online = time_diff < 120 

        result.append({
            "device_name": latest.device_name,
            "lat": latest.latitude,
            "lng": latest.longitude,
            "battery": latest.battery,
            "network": latest.network,
            "time": vn_time.strftime("%H:%M:%S - %d/%m/%Y"),
            "status": "Online" if is_online else "Mất tín hiệu",
            "path": data["path"] # Gửi cả một mảng đường đi cho web vẽ
        })
        
    return jsonify({"devices": result})

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Hệ Thống Theo Dõi Vị Trí Đa Mục Tiêu</title>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        body { margin: 0; padding: 0; display: flex; height: 100vh; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #1e1e1e;}
        #sidebar { width: 380px; background-color: #2c3e50; color: #ecf0f1; display: flex; flex-direction: column; box-shadow: 4px 0 15px rgba(0,0,0,0.5); z-index: 1000; overflow-y: auto; }
        .header { padding: 20px; background-color: #1a252f; text-align: center; font-size: 1.4em; font-weight: bold; border-bottom: 2px solid #34495e; color: #3498db; position: sticky; top: 0; z-index: 10; }
        .device-card { margin: 15px; padding: 15px; background-color: #34495e; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); border-left: 5px solid #3498db; transition: 0.3s; }
        .device-card:hover { transform: translateX(5px); }
        .device-title { font-size: 1.2em; font-weight: bold; margin-bottom: 12px; border-bottom: 1px solid #7f8c8d; padding-bottom: 8px; display: flex; justify-content: space-between; align-items: center;}
        .status-badge { padding: 4px 8px; border-radius: 12px; font-size: 0.65em; text-transform: uppercase; letter-spacing: 1px; }
        .status-online { background-color: #2ecc71; color: #fff; box-shadow: 0 0 10px #2ecc71; }
        .status-offline { background-color: #e74c3c; color: #fff; }
        .info-row { display: flex; justify-content: space-between; margin-bottom: 8px; font-size: 0.9em; color: #bdc3c7; }
        .info-value { color: #fff; font-weight: bold; }
        .network-text { color: #f39c12; font-weight: bold; }
        .battery-container { margin-top: 12px; }
        .battery-text { font-size: 0.8em; margin-bottom: 5px; color: #bdc3c7; }
        .battery-bar { width: 100%; background-color: #2c3e50; border-radius: 6px; height: 10px; overflow: hidden; border: 1px solid #7f8c8d; }
        .battery-level { height: 100%; background-color: #2ecc71; width: 0%; transition: width 0.5s ease-in-out; }
        #map { flex-grow: 1; height: 100vh; }
    </style>
</head>
<body>
    <div id="sidebar">
        <div class="header">🌍 TRUNG TÂM KIỂM SOÁT</div>
        <div id="device-list">
            <div style="padding: 20px; text-align: center; color: #7f8c8d;">Đang quét tín hiệu Radar...</div>
        </div>
    </div>
    <div id="map"></div>

    <script>
        var map = L.map('map').setView([10.0, 106.0], 5);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '© OpenStreetMap' }).addTo(map);
        
        var markers = {};
        var polylines = {};
        var isFirstLoad = true;
        
        // Bảng màu cho tối đa 2 thiết bị: Xanh dương và Đỏ
        var colors = ["#3498db", "#e74c3c"];

        function fetchLocation() {
            fetch('/get_phone')
                .then(response => response.json())
                .then(data => {
                    if (data.devices && data.devices.length > 0) {
                        var sidebarHtml = "";
                        var bounds = []; // Dùng để tính toán khung nhìn bản đồ cho vừa cả 2 thiết bị
                        
                        data.devices.forEach((dev, index) => {
                            var devColor = colors[index % colors.length]; // Gán màu theo thứ tự
                            
                            // ==========================================
                            // 1. CẬP NHẬT DANH SÁCH BÊN TRÁI (UI)
                            // ==========================================
                            var statusClass = (dev.status === "Online") ? "status-online" : "status-offline";
                            var batColor = (dev.battery <= 20) ? "#e74c3c" : "#2ecc71";
                            
                            sidebarHtml += `
                            <div class="device-card" style="border-left-color: ${devColor}">
                                <div class="device-title">
                                    <span><span style="color:${devColor}">●</span> ${dev.device_name}</span>
                                    <span class="status-badge ${statusClass}">${dev.status}</span>
                                </div>
                                <div class="info-row"><span>🌐 Kết nối:</span><span class="info-value network-text">${dev.network}</span></div>
                                <div class="info-row"><span>📍 Vĩ độ:</span><span class="info-value">${dev.lat.toFixed(6)}</span></div>
                                <div class="info-row"><span>📍 Kinh độ:</span><span class="info-value">${dev.lng.toFixed(6)}</span></div>
                                <div class="info-row"><span>⏱️ Cập nhật:</span><span class="info-value">${dev.time}</span></div>
                                <div class="battery-container">
                                    <div class="battery-text">🔋 Tình trạng Pin: <span>${dev.battery}</span>%</div>
                                    <div class="battery-bar"><div class="battery-level" style="width: ${Math.min(dev.battery, 100)}%; background-color: ${batColor}"></div></div>
                                </div>
                            </div>`;
                            
                            // ==========================================
                            // 2. VẼ LÊN BẢN ĐỒ
                            // ==========================================
                            var currentLatLng = new L.LatLng(dev.lat, dev.lng);
                            bounds.push(currentLatLng);

                            // A. Chấm vị trí hiện tại (Marker)
                            if (!markers[dev.device_name]) {
                                markers[dev.device_name] = L.marker(currentLatLng).addTo(map)
                                    .bindPopup("<b>" + dev.device_name + "</b><br>Pin: " + dev.battery + "%");
                            } else {
                                markers[dev.device_name].setLatLng(currentLatLng);
                            }

                            // B. Vẽ lịch sử vết đường đi (Polyline)
                            if (!polylines[dev.device_name]) {
                                polylines[dev.device_name] = L.polyline(dev.path, {
                                    color: devColor, 
                                    weight: 5, 
                                    opacity: 0.7, 
                                    lineJoin: 'round'
                                }).addTo(map);
                            } else {
                                polylines[dev.device_name].setLatLngs(dev.path);
                            }
                        });
                        
                        document.getElementById('device-list').innerHTML = sidebarHtml;

                        // Nếu là lần đầu tiên có dữ liệu, Zoom bản đồ sao cho bao trọn các thiết bị
                        if (isFirstLoad && bounds.length > 0) {
                            var group = new L.featureGroup(Object.values(markers));
                            map.fitBounds(group.getBounds(), {padding: [50, 50], maxZoom: 16});
                            isFirstLoad = false;
                        }
                    } else {
                        document.getElementById('device-list').innerHTML = '<div style="padding: 20px; text-align: center; color: #7f8c8d;">Chưa có thiết bị nào trong 24h qua</div>';
                    }
                })
                .catch(err => console.log("Đang chờ dữ liệu..."));
        }
        setInterval(fetchLocation, 2000); // Tự động quét 2 giây/lần
        fetchLocation();
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

if __name__ == '__main__':
    pass